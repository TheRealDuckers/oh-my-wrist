"""
test_end_to_end_normalization.py — End-to-end pipeline tests.

Tests the full path:
  raw JSON payload (Claude Code or OpenCode)
  → adapter (claude_adapter / opencode_adapter)
  → CanonicalEvent
  → history_encoder.encode_event()
  → BLE binary frame (≤ MAX_FRAME_LEN bytes)

Also tests:
  → SessionState.on_event()
  → SessionState.to_ble_payload() (≤ MAX_STATS_LEN bytes)

Simulates a complete realistic Claude Code session and a complete
realistic OpenCode session, verifying every step of the pipeline.
"""

from __future__ import annotations

import json

import pytest

from ohm.adapters.claude_adapter import adapt_claude_hook
from ohm.adapters.opencode_adapter import (
    adapt_opencode_event,
    clear_debounce_cache,
    clear_status_cache,
)
from ohm.history_encoder import decode_frame, encode_event
from ohm.icons import IconId
from ohm.protocol import HookEvent, MAX_FRAME_LEN, MAX_STATS_LEN
from ohm.session_state import SessionState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _claude_raw(
    event: str,
    tool_name: str | None = None,
    tool_input: dict | None = None,
    session_id: str | None = "sess-claude",
) -> dict:
    payload: dict = {"event": event}
    if tool_name:
        payload["tool_name"] = tool_name
    if tool_input is not None:
        payload["tool_input"] = tool_input
    if session_id:
        payload["session_id"] = session_id
    return payload


def _oc_raw(provider_event: str, **kwargs) -> dict:
    return {"provider_event": provider_event, **kwargs}


def _decode(ev) -> dict:
    frame = encode_event(ev)
    assert len(frame) <= MAX_FRAME_LEN, (
        f"Frame too long: {len(frame)} bytes for {ev.canonical_event}"
    )
    decoded = decode_frame(frame)
    assert decoded is not None
    return decoded


@pytest.fixture(autouse=True)
def reset_oc_caches():
    clear_debounce_cache()
    clear_status_cache()
    yield
    clear_debounce_cache()
    clear_status_cache()


# ---------------------------------------------------------------------------
# Single-event round-trips — Claude Code
# ---------------------------------------------------------------------------


class TestClaudeRoundTrip:
    @pytest.mark.parametrize(
        "raw,expected_icon",
        [
            (_claude_raw("PreToolUse", "Bash", {"command": "git status"}), IconId.PLAY),
            (_claude_raw("PreToolUse", "Edit", {"path": "main.py"}), IconId.PENCIL),
            (_claude_raw("PreToolUse", "Write", {"path": "out.txt"}), IconId.PENCIL),
            (_claude_raw("PreToolUse", "Read", {"path": "/etc/hosts"}), IconId.EYE),
            (_claude_raw("PreToolUse", "WebFetch", {"url": "https://x"}), IconId.GLOBE),
            (
                _claude_raw("PreToolUse", "WebSearch", {"query": "p async"}),
                IconId.GLOBE,
            ),
            (_claude_raw("PreToolUse", "TodoWrite", {}), IconId.CLIPBOARD),
            (_claude_raw("PreToolUse", "Agent", {}), IconId.WRENCH),
            (_claude_raw("PostToolUse", "Bash", {"command": "ls"}), IconId.CHECK),
            (_claude_raw("Notification"), IconId.PAUSE),
            (_claude_raw("Stop"), IconId.STOP),
        ],
    )
    def test_icon(self, raw, expected_icon):
        hook = HookEvent.model_validate(raw)
        canonical = adapt_claude_hook(hook, raw_payload=raw)
        decoded = _decode(canonical)
        assert decoded["icon"] == int(expected_icon)

    @pytest.mark.parametrize(
        "raw",
        [
            _claude_raw("PreToolUse", "Bash", {"command": "git status"}),
            _claude_raw("PreToolUse", "Edit", {"path": "a" * 100}),
            _claude_raw("PreToolUse", "Write", {"path": "b" * 100}),
            _claude_raw("PostToolUse", "Bash"),
            _claude_raw("Notification"),
            _claude_raw("Stop"),
        ],
    )
    def test_frame_byte_limit(self, raw):
        hook = HookEvent.model_validate(raw)
        canonical = adapt_claude_hook(hook, raw_payload=raw)
        _decode(canonical)

    def test_long_command_truncated(self):
        raw = _claude_raw("PreToolUse", "Bash", {"command": "echo " + "x" * 200})
        hook = HookEvent.model_validate(raw)
        canonical = adapt_claude_hook(hook)
        decoded = _decode(canonical)
        # "echo" is the first word — it fits whole, so the text is just "echo"
        assert decoded["icon"] == int(IconId.PLAY)
        assert decoded["text"].startswith("echo")

    def test_unicode_path_truncated(self):
        raw = _claude_raw("PreToolUse", "Edit", {"path": "ファイル" * 20})
        hook = HookEvent.model_validate(raw)
        canonical = adapt_claude_hook(hook)
        decoded = _decode(canonical)
        # Text must still decode cleanly (multi-byte not split)
        assert isinstance(decoded["text"], str)

    def test_multibyte_path_truncated(self):
        raw = _claude_raw("PreToolUse", "Write", {"path": "ファイル" * 10})
        hook = HookEvent.model_validate(raw)
        canonical = adapt_claude_hook(hook)
        _decode(canonical)


# ---------------------------------------------------------------------------
# Single-event round-trips — OpenCode
# ---------------------------------------------------------------------------


class TestOpenCodeRoundTrip:
    @pytest.mark.parametrize(
        "raw,expected_icon",
        [
            (
                _oc_raw(
                    "tool.execute.before",
                    tool_name="Bash",
                    label="npm test",
                    session_id="s1",
                ),
                IconId.PLAY,
            ),
            (
                _oc_raw(
                    "tool.execute.before",
                    tool_name="Edit",
                    label="app.py",
                    session_id="s2",
                ),
                IconId.PENCIL,
            ),
            (
                _oc_raw(
                    "tool.execute.before",
                    tool_name="Write",
                    label="out.txt",
                    session_id="s3",
                ),
                IconId.PENCIL,
            ),
            (
                _oc_raw(
                    "tool.execute.before",
                    tool_name="Read",
                    label="/etc/hosts",
                    session_id="s4",
                ),
                IconId.EYE,
            ),
            (
                _oc_raw(
                    "tool.execute.before",
                    tool_name="WebFetch",
                    label="https://x",
                    session_id="s5",
                ),
                IconId.GLOBE,
            ),
            (
                _oc_raw("tool.execute.after", tool_name="Bash", session_id="s6"),
                IconId.CHECK,
            ),
            (_oc_raw("session.idle", session_id="s7"), IconId.PAUSE),
            (_oc_raw("session.completed", session_id="s8"), IconId.STOP),
            (_oc_raw("session.error", session_id="s9"), IconId.WARNING),
        ],
    )
    def test_icon(self, raw, expected_icon):
        canonical = adapt_opencode_event(raw)
        if canonical is None:
            pytest.skip("Event suppressed")
        decoded = _decode(canonical)
        assert decoded["icon"] == int(expected_icon)

    @pytest.mark.parametrize(
        "raw",
        [
            _oc_raw(
                "tool.execute.before",
                tool_name="Bash",
                label="a" * 200,
                session_id="s1",
            ),
            _oc_raw(
                "tool.execute.before",
                tool_name="Edit",
                label="ファイル" * 20,
                session_id="s2",
            ),
            _oc_raw(
                "tool.execute.before",
                tool_name="Write",
                label="données" * 10,
                session_id="s3",
            ),
            _oc_raw("session.idle", session_id="s4"),
            _oc_raw("session.completed", session_id="s5"),
        ],
    )
    def test_frame_byte_limit(self, raw):
        canonical = adapt_opencode_event(raw)
        if canonical is None:
            pytest.skip("Event suppressed")
        _decode(canonical)


# ---------------------------------------------------------------------------
# Full Claude Code session simulation
# ---------------------------------------------------------------------------


CLAUDE_SESSION = [
    (
        _claude_raw("PreToolUse", "Read", {"path": "README.md"}),
        IconId.EYE,
        "Read README",
    ),
    (_claude_raw("PostToolUse", "Read"), IconId.CHECK, "Read done"),
    (
        _claude_raw("PreToolUse", "Bash", {"command": "git log --oneline"}),
        IconId.PLAY,
        "Git log",
    ),
    (_claude_raw("PostToolUse", "Bash"), IconId.CHECK, "Git log done"),
    (
        _claude_raw("PreToolUse", "Edit", {"path": "src/main.py"}),
        IconId.PENCIL,
        "Edit main",
    ),
    (_claude_raw("PostToolUse", "Edit"), IconId.CHECK, "Edit done"),
    (
        _claude_raw("PreToolUse", "Write", {"path": "src/util.py"}),
        IconId.PENCIL,
        "Write util",
    ),
    (_claude_raw("PostToolUse", "Write"), IconId.CHECK, "Write done"),
    (
        _claude_raw("PreToolUse", "Bash", {"command": "pytest -x"}),
        IconId.PLAY,
        "Run tests",
    ),
    (_claude_raw("PostToolUse", "Bash"), IconId.CHECK, "Tests done"),
    (
        _claude_raw("PreToolUse", "WebSearch", {"query": "pydantic v2"}),
        IconId.GLOBE,
        "Web search",
    ),
    (_claude_raw("PostToolUse", "WebSearch"), IconId.CHECK, "Search done"),
    (_claude_raw("PreToolUse", "TodoWrite", {}), IconId.CLIPBOARD, "Todo update"),
    (_claude_raw("PostToolUse", "TodoWrite"), IconId.CHECK, "Todo done"),
    (_claude_raw("Notification"), IconId.PAUSE, "Idle"),
    (_claude_raw("PreToolUse", "Agent", {}), IconId.WRENCH, "Agent"),
    (_claude_raw("PostToolUse", "Agent"), IconId.CHECK, "Agent done"),
    (_claude_raw("Stop"), IconId.STOP, "Session stop"),
]


class TestClaudeSessionSimulation:
    @pytest.mark.parametrize("raw,expected_icon,desc", CLAUDE_SESSION)
    def test_step(self, raw, expected_icon, desc):
        hook = HookEvent.model_validate(raw)
        canonical = adapt_claude_hook(hook, raw_payload=raw)
        decoded = _decode(canonical)
        assert decoded["icon"] == int(expected_icon), (
            f"[{desc}] expected icon {expected_icon!r}, got {decoded['icon']:#x}"
        )

    def test_session_state_after_full_session(self):
        s = SessionState()
        for raw, _, _ in CLAUDE_SESSION:
            hook = HookEvent.model_validate(raw)
            canonical = adapt_claude_hook(hook, raw_payload=raw)
            s.on_event(canonical)

        assert s.is_active is False
        assert s.bash_count == 2
        assert len(s.edited_files) == 2  # main.py and util.py
        assert s.last_completion_time is not None

        payload = s.to_ble_payload()
        assert len(payload) <= MAX_STATS_LEN
        data = json.loads(payload)
        assert data["b"] == 2
        assert data["e"] == 2
        assert data["t"] > 0


# ---------------------------------------------------------------------------
# Full OpenCode session simulation
# ---------------------------------------------------------------------------


OPENCODE_SESSION = [
    (_oc_raw("session.created", session_id="oc-1"), None, "Session start"),
    (
        _oc_raw(
            "tool.execute.before",
            tool_name="Read",
            label="README.md",
            session_id="oc-1",
        ),
        IconId.EYE,
        "Read README",
    ),
    (
        _oc_raw("tool.execute.after", tool_name="Read", session_id="oc-1"),
        IconId.CHECK,
        "Read done",
    ),
    (
        _oc_raw(
            "tool.execute.before",
            tool_name="Bash",
            label="git status",
            session_id="oc-1",
        ),
        IconId.PLAY,
        "Git status",
    ),
    (
        _oc_raw("tool.execute.after", tool_name="Bash", session_id="oc-1"),
        IconId.CHECK,
        "Bash done",
    ),
    (
        _oc_raw(
            "tool.execute.before", tool_name="Edit", label="app.py", session_id="oc-1"
        ),
        IconId.PENCIL,
        "Edit app",
    ),
    (_oc_raw("file.edited", path="app.py", session_id="oc-1"), None, "File edited"),
    (
        _oc_raw("tool.execute.after", tool_name="Edit", session_id="oc-1"),
        IconId.CHECK,
        "Edit done",
    ),
    (_oc_raw("session.idle", session_id="oc-1"), IconId.PAUSE, "Idle"),
    (
        _oc_raw(
            "tool.execute.before", tool_name="Write", label="out.txt", session_id="oc-1"
        ),
        IconId.PENCIL,
        "Write out",
    ),
    (
        _oc_raw("tool.execute.after", tool_name="Write", session_id="oc-1"),
        IconId.CHECK,
        "Write done",
    ),
    (_oc_raw("todo.updated", session_id="oc-1"), None, "Todo updated"),
    (_oc_raw("session.completed", session_id="oc-1"), IconId.STOP, "Session done"),
]


class TestOpenCodeSessionSimulation:
    @pytest.mark.parametrize("raw,expected_icon,desc", OPENCODE_SESSION)
    def test_step(self, raw, expected_icon, desc):
        canonical = adapt_opencode_event(raw)
        if canonical is None:
            pytest.skip(f"[{desc}] Event suppressed by noise control")
        decoded = _decode(canonical)
        if expected_icon is not None:
            assert decoded["icon"] == int(expected_icon), (
                f"[{desc}] expected icon {expected_icon!r}, got {decoded['icon']:#x}"
            )

    def test_session_state_after_full_opencode_session(self):
        s = SessionState()
        for raw, _, _ in OPENCODE_SESSION:
            canonical = adapt_opencode_event(raw)
            if canonical is not None:
                s.on_event(canonical)

        assert s.is_active is False
        assert s.bash_count == 1
        assert s.last_completion_time is not None

        payload = s.to_ble_payload()
        assert len(payload) <= MAX_STATS_LEN
        data = json.loads(payload)
        assert data["b"] == 1
        assert data["t"] > 0


# ---------------------------------------------------------------------------
# Cross-provider normalization
# ---------------------------------------------------------------------------


class TestCrossProviderNormalization:
    """Equivalent events from both providers must produce the same icon ID."""

    @pytest.mark.parametrize(
        "claude_raw,oc_raw,expected_icon",
        [
            (
                _claude_raw("PreToolUse", "Bash", {"command": "ls"}),
                _oc_raw(
                    "tool.execute.before", tool_name="Bash", label="ls", session_id="x1"
                ),
                IconId.PLAY,
            ),
            (
                _claude_raw("PreToolUse", "Edit", {"path": "a.py"}),
                _oc_raw(
                    "tool.execute.before",
                    tool_name="Edit",
                    label="a.py",
                    session_id="x2",
                ),
                IconId.PENCIL,
            ),
            (
                _claude_raw("PostToolUse", "Bash"),
                _oc_raw("tool.execute.after", tool_name="Bash", session_id="x3"),
                IconId.CHECK,
            ),
            (
                _claude_raw("Notification"),
                _oc_raw("session.idle", session_id="x4"),
                IconId.PAUSE,
            ),
            (
                _claude_raw("Stop"),
                _oc_raw("session.completed", session_id="x5"),
                IconId.STOP,
            ),
        ],
    )
    def test_same_icon(self, claude_raw, oc_raw, expected_icon):
        claude_hook = HookEvent.model_validate(claude_raw)
        claude_canonical = adapt_claude_hook(claude_hook)
        claude_decoded = _decode(claude_canonical)

        oc_canonical = adapt_opencode_event(oc_raw)
        if oc_canonical is None:
            pytest.skip("OpenCode event suppressed")
        oc_decoded = _decode(oc_canonical)

        assert claude_decoded["icon"] == int(expected_icon)
        assert oc_decoded["icon"] == int(expected_icon)

    def test_canonical_event_matches(self):
        """PreToolUse/Bash and tool.execute.before/Bash both produce tool_start."""
        claude_hook = HookEvent.model_validate(
            _claude_raw("PreToolUse", "Bash", {"command": "ls"})
        )
        claude_canonical = adapt_claude_hook(claude_hook)

        oc_canonical = adapt_opencode_event(
            _oc_raw(
                "tool.execute.before", tool_name="Bash", label="ls", session_id="y1"
            )
        )
        assert oc_canonical is not None

        assert claude_canonical.canonical_event == "tool_start"
        assert oc_canonical.canonical_event == "tool_start"

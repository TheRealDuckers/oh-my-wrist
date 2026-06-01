"""
test_session_state.py — Tests for session_state.py.

Covers:
- Initial state
- on_event() for all canonical event types
- Per-provider counting
- Per-intent counting
- Idle timer start/stop/accumulation
- Edited file deduplication
- Bash/shell command counting
- session_start resets all stats
- session_stop sets is_active=False and records completion time
- reset() reinitialises
- to_ble_payload() byte limit, JSON validity, all keys present
- Provider initial in payload ("C" / "O")
- Realistic multi-provider session simulation
"""

from __future__ import annotations

import json
import time
from unittest.mock import patch


from ohm.protocol import MAX_STATS_LEN
from ohm.provider_types import CanonicalEvent
from ohm.session_state import MultiProviderSessionState, SessionState


def _ev(canonical_event: str, provider: str = "claude", **kwargs) -> CanonicalEvent:
    return CanonicalEvent(provider=provider, canonical_event=canonical_event, **kwargs)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_is_active_false(self):
        s = SessionState()
        assert s.is_active is False

    def test_tool_calls_zero(self):
        s = SessionState()
        assert s.tool_calls == 0

    def test_edited_files_empty(self):
        s = SessionState()
        assert len(s.edited_files) == 0

    def test_bash_count_zero(self):
        s = SessionState()
        assert s.bash_count == 0

    def test_idle_seconds_zero(self):
        s = SessionState()
        assert s.idle_seconds == 0.0

    def test_provider_counts_empty(self):
        s = SessionState()
        assert s.provider_counts == {}

    def test_intent_counts_empty(self):
        s = SessionState()
        assert s.intent_counts == {}

    def test_last_completion_none(self):
        s = SessionState()
        assert s.last_completion_time is None


# ---------------------------------------------------------------------------
# tool_calls increment
# ---------------------------------------------------------------------------


class TestToolCallsIncrement:
    def test_increments_on_every_event(self):
        s = SessionState()
        for i in range(5):
            s.on_event(_ev("tool_start", tool_name="Bash", label="ls"))
        assert s.tool_calls == 5

    def test_increments_on_non_tool_events(self):
        s = SessionState()
        s.on_event(_ev("session_idle"))
        s.on_event(_ev("tool_end"))
        assert s.tool_calls == 2


# ---------------------------------------------------------------------------
# Per-provider counting
# ---------------------------------------------------------------------------


class TestProviderCounting:
    def test_claude_events_counted(self):
        s = SessionState()
        s.on_event(_ev("tool_start", provider="claude"))
        s.on_event(_ev("tool_end", provider="claude"))
        assert s.provider_counts["claude"] == 2

    def test_opencode_events_counted(self):
        s = SessionState()
        s.on_event(_ev("tool_start", provider="opencode"))
        assert s.provider_counts["opencode"] == 1

    def test_mixed_providers(self):
        s = SessionState()
        s.on_event(_ev("tool_start", provider="claude"))
        s.on_event(_ev("tool_start", provider="opencode"))
        s.on_event(_ev("tool_end", provider="claude"))
        assert s.provider_counts["claude"] == 2
        assert s.provider_counts["opencode"] == 1

    def test_last_provider_updated(self):
        s = SessionState()
        s.on_event(_ev("tool_start", provider="claude"))
        assert s.last_provider == "claude"
        s.on_event(_ev("tool_start", provider="opencode"))
        assert s.last_provider == "opencode"


# ---------------------------------------------------------------------------
# Per-intent counting
# ---------------------------------------------------------------------------


class TestIntentCounting:
    def test_shell_intent_counted(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Bash"))
        assert s.intent_counts.get("shell", 0) == 1

    def test_edit_intent_counted(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Edit"))
        assert s.intent_counts.get("edit", 0) == 1

    def test_multiple_intents(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Bash"))
        s.on_event(_ev("tool_start", tool_name="Edit"))
        s.on_event(_ev("tool_start", tool_name="Bash"))
        assert s.intent_counts["shell"] == 2
        assert s.intent_counts["edit"] == 1


# ---------------------------------------------------------------------------
# Bash/shell command counting
# ---------------------------------------------------------------------------


class TestBashCounting:
    def test_bash_tool_increments(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Bash"))
        assert s.bash_count == 1

    def test_shell_tool_increments(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Shell"))
        assert s.bash_count == 1

    def test_run_tool_increments(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Run"))
        assert s.bash_count == 1

    def test_non_shell_does_not_increment(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Edit"))
        assert s.bash_count == 0

    def test_multiple_bash_events(self):
        s = SessionState()
        for _ in range(7):
            s.on_event(_ev("tool_start", tool_name="Bash"))
        assert s.bash_count == 7

    def test_tool_end_does_not_increment(self):
        s = SessionState()
        s.on_event(_ev("tool_end", tool_name="Bash"))
        assert s.bash_count == 0


# ---------------------------------------------------------------------------
# Edited file tracking
# ---------------------------------------------------------------------------


class TestEditedFiles:
    def test_edit_tool_adds_path(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Edit", path="/src/app.py"))
        assert "/src/app.py" in s.edited_files

    def test_write_tool_adds_path(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Write", path="/src/lib.py"))
        assert "/src/lib.py" in s.edited_files

    def test_file_edit_event_adds_path(self):
        s = SessionState()
        s.on_event(_ev("file_edit", path="/src/config.py"))
        assert "/src/config.py" in s.edited_files

    def test_duplicate_paths_deduplicated(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Edit", path="/src/app.py"))
        s.on_event(_ev("tool_start", tool_name="Edit", path="/src/app.py"))
        assert len(s.edited_files) == 1

    def test_no_path_does_not_add(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Edit"))
        assert len(s.edited_files) == 0

    def test_bash_does_not_add_to_files(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Bash", path="/src/app.py"))
        assert len(s.edited_files) == 0


# ---------------------------------------------------------------------------
# Idle timer
# ---------------------------------------------------------------------------


class TestIdleTimer:
    def test_idle_starts_on_session_idle(self):
        s = SessionState()
        s.on_event(_ev("session_idle"))
        assert s.last_idle_start is not None

    def test_idle_stops_on_tool_start(self):
        s = SessionState()
        s.on_event(_ev("session_idle"))
        time.sleep(0.01)
        s.on_event(_ev("tool_start", tool_name="Bash"))
        assert s.last_idle_start is None
        assert s.idle_seconds > 0

    def test_idle_stops_on_tool_end(self):
        s = SessionState()
        s.on_event(_ev("session_idle"))
        s.on_event(_ev("tool_end"))
        assert s.last_idle_start is None

    def test_idle_accumulates_across_multiple_windows(self):
        s = SessionState()
        # on_event calls time.time() once at entry; _stop_idle_timer uses that same `now`.
        # Sequence: session_idle(now=100), tool_start(now=101), session_idle(now=102), tool_start(now=103)
        # Window 1: 101 - 100 = 1.0s; Window 2: 103 - 102 = 1.0s; total = 2.0s
        with patch("time.time", side_effect=[100.0, 101.0, 102.0, 103.0]):
            s.on_event(_ev("session_idle"))  # now=100, idle_start=100
            s.on_event(_ev("tool_start", tool_name="Bash"))  # now=101, stop: +1.0s
            s.on_event(_ev("session_idle"))  # now=102, idle_start=102
            s.on_event(_ev("tool_start", tool_name="Edit"))  # now=103, stop: +1.0s
        assert abs(s.idle_seconds - 2.0) < 0.01

    def test_open_idle_window_included_in_payload(self):
        s = SessionState()
        s.on_event(_ev("session_idle"))
        payload = json.loads(s.to_ble_payload())
        assert payload["i"] >= 0


# ---------------------------------------------------------------------------
# session_start resets stats
# ---------------------------------------------------------------------------


class TestSessionStart:
    def test_session_start_resets_tool_calls(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Bash"))
        s.on_event(_ev("tool_start", tool_name="Bash"))
        s.on_event(_ev("session_start"))
        assert s.tool_calls == 1  # session_start itself counts as 1

    def test_session_start_resets_edited_files(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Edit", path="/a.py"))
        s.on_event(_ev("session_start"))
        assert len(s.edited_files) == 0

    def test_session_start_resets_bash_count(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Bash"))
        s.on_event(_ev("session_start"))
        assert s.bash_count == 0

    def test_session_start_resets_idle(self):
        s = SessionState()
        s.on_event(_ev("session_idle"))
        s.on_event(_ev("tool_start", tool_name="Bash"))
        s.on_event(_ev("session_start"))
        assert s.idle_seconds == 0.0

    def test_session_start_sets_is_active(self):
        s = SessionState()
        s.on_event(_ev("session_start"))
        assert s.is_active is True

    def test_session_start_resets_provider_counts(self):
        s = SessionState()
        s.on_event(_ev("tool_start", provider="claude"))
        s.on_event(_ev("session_start", provider="opencode"))
        assert s.provider_counts == {"opencode": 1}


# ---------------------------------------------------------------------------
# session_stop
# ---------------------------------------------------------------------------


class TestSessionStop:
    def test_session_stop_sets_inactive(self):
        s = SessionState()
        s.on_event(_ev("session_start"))
        s.on_event(_ev("session_stop"))
        assert s.is_active is False

    def test_session_stop_records_completion_time(self):
        s = SessionState()
        before = time.time()
        s.on_event(_ev("session_stop"))
        after = time.time()
        assert s.last_completion_time is not None
        assert before <= s.last_completion_time <= after

    def test_session_error_sets_inactive(self):
        s = SessionState()
        s.on_event(_ev("session_start"))
        s.on_event(_ev("session_error"))
        assert s.is_active is False

    def test_session_stop_stops_idle_timer(self):
        s = SessionState()
        s.on_event(_ev("session_idle"))
        s.on_event(_ev("session_stop"))
        assert s.last_idle_start is None


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_all_state(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Bash", path="/a.py"))
        s.on_event(_ev("session_idle"))
        s.reset()
        assert s.tool_calls == 0
        assert s.bash_count == 0
        assert len(s.edited_files) == 0
        assert s.idle_seconds == 0.0
        assert s.is_active is False
        assert s.provider_counts == {}


# ---------------------------------------------------------------------------
# to_ble_payload()
# ---------------------------------------------------------------------------


class TestBlePaylod:
    def test_payload_is_bytes(self):
        s = SessionState()
        assert isinstance(s.to_ble_payload(), bytes)

    def test_payload_valid_json(self):
        s = SessionState()
        data = json.loads(s.to_ble_payload())
        assert isinstance(data, dict)

    def test_payload_has_required_keys(self):
        s = SessionState()
        data = json.loads(s.to_ble_payload())
        for key in ("d", "t", "e", "b", "i", "s", "p"):
            assert key in data, f"Missing key: {key}"

    def test_payload_within_byte_limit(self):
        s = SessionState()
        for i in range(100):
            s.on_event(_ev("tool_start", tool_name="Edit", path=f"/src/file{i}.py"))
        payload = s.to_ble_payload()
        assert len(payload) <= MAX_STATS_LEN

    def test_provider_id_claude(self):
        s = SessionState()
        s.on_event(_ev("tool_start", provider="claude"))
        data = json.loads(s.to_ble_payload())
        assert data.get("p") == 1

    def test_provider_id_opencode(self):
        s = SessionState()
        s.on_event(_ev("tool_start", provider="opencode"))
        data = json.loads(s.to_ble_payload())
        assert data.get("p") == 2

    def test_completion_never_when_no_stop(self):
        s = SessionState()
        data = json.loads(s.to_ble_payload())
        assert data["s"] == -1

    def test_completion_seconds_ago(self):
        s = SessionState()
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            s.on_event(_ev("session_stop"))
            mock_time.return_value = 1030.0
            data = json.loads(s.to_ble_payload())
        assert data["s"] == 30

    def test_completion_minutes_ago(self):
        s = SessionState()
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            s.on_event(_ev("session_stop"))
            mock_time.return_value = 1000.0 + 180
            data = json.loads(s.to_ble_payload())
        assert data["s"] == 180

    def test_edited_files_count(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Edit", path="/a.py"))
        s.on_event(_ev("tool_start", tool_name="Edit", path="/b.py"))
        s.on_event(_ev("tool_start", tool_name="Edit", path="/a.py"))  # duplicate
        data = json.loads(s.to_ble_payload())
        assert data["e"] == 2

    def test_bash_count_in_payload(self):
        s = SessionState()
        s.on_event(_ev("tool_start", tool_name="Bash"))
        s.on_event(_ev("tool_start", tool_name="Bash"))
        data = json.loads(s.to_ble_payload())
        assert data["b"] == 2

    def test_payload_utf8_decodable(self):
        s = SessionState()
        payload = s.to_ble_payload()
        decoded = payload.decode("utf-8")
        assert decoded  # non-empty


# ---------------------------------------------------------------------------
# Realistic multi-provider session simulation
# ---------------------------------------------------------------------------


class TestRealisticSession:
    def test_full_session_with_both_providers(self):
        """Simulate a realistic session mixing Claude Code and OpenCode events."""
        s = SessionState()

        # Session starts (Claude)
        s.on_event(_ev("session_start", provider="claude"))
        assert s.is_active is True

        # Claude reads a file
        s.on_event(
            _ev("tool_start", provider="claude", tool_name="Read", path="/src/main.py")
        )
        s.on_event(_ev("tool_end", provider="claude", tool_name="Read"))

        # OpenCode edits a file
        s.on_event(
            _ev("tool_start", provider="opencode", tool_name="Edit", path="/src/app.py")
        )
        s.on_event(_ev("tool_end", provider="opencode", tool_name="Edit"))

        # Claude runs a bash command
        s.on_event(_ev("tool_start", provider="claude", tool_name="Bash"))
        s.on_event(_ev("tool_end", provider="claude", tool_name="Bash"))

        # Session goes idle
        s.on_event(_ev("session_idle", provider="claude"))

        # Claude resumes
        s.on_event(
            _ev("tool_start", provider="claude", tool_name="Write", path="/src/new.py")
        )
        s.on_event(_ev("tool_end", provider="claude", tool_name="Write"))

        # OpenCode edits same file (dedup test)
        s.on_event(
            _ev("tool_start", provider="opencode", tool_name="Edit", path="/src/app.py")
        )
        s.on_event(_ev("tool_end", provider="opencode", tool_name="Edit"))

        # Session stops
        s.on_event(_ev("session_stop", provider="claude"))

        # Verify stats
        assert s.is_active is False
        assert s.bash_count == 1
        assert len(s.edited_files) == 2  # app.py and new.py
        assert s.provider_counts["claude"] >= 1
        assert s.provider_counts["opencode"] >= 1
        assert s.last_completion_time is not None

        # BLE payload valid
        payload = s.to_ble_payload()
        assert len(payload) <= MAX_STATS_LEN
        data = json.loads(payload)
        assert data["b"] == 1
        assert data["e"] == 2
        assert data["t"] > 0


# ---------------------------------------------------------------------------
# MultiProviderSessionState
# ---------------------------------------------------------------------------


class TestMultiProvider:
    def test_routing_separates_counters(self):
        m = MultiProviderSessionState()
        m.on_event(_ev("tool_start", provider="claude", tool_name="Bash"))
        m.on_event(_ev("tool_start", provider="claude", tool_name="Bash"))
        m.on_event(
            _ev("tool_start", provider="opencode", tool_name="Edit", path="/a.py")
        )

        claude = m.state_for("claude")
        opencode = m.state_for("opencode")

        assert claude.bash_count == 2
        assert opencode.bash_count == 0
        assert len(claude.edited_files) == 0
        assert len(opencode.edited_files) == 1

    def test_claude_session_start_does_not_reset_opencode(self):
        m = MultiProviderSessionState()

        # Build up OpenCode state first.
        m.on_event(
            _ev("tool_start", provider="opencode", tool_name="Edit", path="/a.py")
        )
        m.on_event(
            _ev("tool_start", provider="opencode", tool_name="Edit", path="/b.py")
        )
        opencode_files_before = len(m.state_for("opencode").edited_files)
        assert opencode_files_before == 2

        # Claude session_start should leave OpenCode untouched.
        m.on_event(_ev("session_start", provider="claude"))

        assert len(m.state_for("opencode").edited_files) == 2
        assert m.state_for("claude").tool_calls == 1  # session_start counted

    def test_opencode_session_start_does_not_reset_claude(self):
        m = MultiProviderSessionState()
        m.on_event(_ev("tool_start", provider="claude", tool_name="Bash"))
        m.on_event(_ev("tool_start", provider="claude", tool_name="Bash"))
        assert m.state_for("claude").bash_count == 2

        m.on_event(_ev("session_start", provider="opencode"))

        assert m.state_for("claude").bash_count == 2
        assert m.state_for("opencode").is_active is True

    def test_payload_for_reflects_only_that_provider(self):
        m = MultiProviderSessionState()
        m.on_event(_ev("tool_start", provider="claude", tool_name="Bash"))
        m.on_event(_ev("tool_start", provider="claude", tool_name="Bash"))
        m.on_event(
            _ev("tool_start", provider="opencode", tool_name="Edit", path="/a.py")
        )

        claude_data = json.loads(m.payload_for("claude"))
        opencode_data = json.loads(m.payload_for("opencode"))

        assert claude_data["b"] == 2
        assert claude_data["e"] == 0
        assert opencode_data["b"] == 0
        assert opencode_data["e"] == 1

    def test_payload_provider_id_per_state(self):
        m = MultiProviderSessionState()
        m.on_event(_ev("tool_start", provider="claude", tool_name="Bash"))
        m.on_event(
            _ev("tool_start", provider="opencode", tool_name="Edit", path="/a.py")
        )

        # Each state's last_provider is its own provider — payload "p" reflects that.
        assert json.loads(m.payload_for("claude"))["p"] == 1
        assert json.loads(m.payload_for("opencode"))["p"] == 2

    def test_reset_only_targets_one_provider(self):
        m = MultiProviderSessionState()
        m.on_event(_ev("tool_start", provider="claude", tool_name="Bash"))
        m.on_event(
            _ev("tool_start", provider="opencode", tool_name="Edit", path="/a.py")
        )

        m.reset("claude")

        assert m.state_for("claude").bash_count == 0
        assert m.state_for("claude").tool_calls == 0
        assert m.state_for("opencode").tool_calls == 1
        assert len(m.state_for("opencode").edited_files) == 1

    def test_any_active(self):
        m = MultiProviderSessionState()
        assert m.any_active() is False

        m.on_event(_ev("session_start", provider="claude"))
        assert m.any_active() is True

        m.on_event(_ev("session_stop", provider="claude"))
        assert m.any_active() is False

        m.on_event(_ev("session_start", provider="opencode"))
        m.on_event(_ev("session_start", provider="claude"))
        m.on_event(_ev("session_stop", provider="claude"))
        # OpenCode still active
        assert m.any_active() is True

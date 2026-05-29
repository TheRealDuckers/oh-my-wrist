"""
test_opencode_adapter.py — Tests for adapters/opencode_adapter.py.

Covers:
- All OpenCode event → CanonicalEvent mappings
- ANSI stripping and whitespace normalisation
- Debounce suppression for tool.execute.before
- session.updated suppression when status unchanged
- Label extraction for each event type
- Path extraction from top-level and meta
- permission_reply approved/denied logic
- Returns None for suppressed events
- clear_debounce_cache() and clear_status_cache() utilities
"""

from __future__ import annotations

import time

import pytest

from ohm.adapters.opencode_adapter import (
    adapt_opencode_event,
    clear_debounce_cache,
    clear_status_cache,
)


def _ev(provider_event: str, **kwargs) -> dict:
    """Build a minimal OpenCode event payload."""
    return {"provider_event": provider_event, **kwargs}


@pytest.fixture(autouse=True)
def reset_caches():
    """Clear debounce and status caches before every test."""
    clear_debounce_cache()
    clear_status_cache()
    yield
    clear_debounce_cache()
    clear_status_cache()


# ---------------------------------------------------------------------------
# Canonical event mapping
# ---------------------------------------------------------------------------


class TestCanonicalMapping:
    @pytest.mark.parametrize(
        "oc_event,expected",
        [
            ("tool.execute.before", "tool_start"),
            ("tool.execute.after", "tool_end"),
            ("session.created", "session_start"),
            ("session.idle", "session_idle"),
            ("session.status", "status"),
            ("session.error", "session_error"),
            ("session.updated", "status"),
            ("file.edited", "file_edit"),
            ("todo.updated", "todo_update"),
            ("permission.asked", "permission_request"),
            ("permission.replied", "permission_reply"),
            ("command.executed", "command"),
        ],
    )
    def test_mapping(self, oc_event, expected):
        result = adapt_opencode_event(_ev(oc_event))
        if result is None:
            pytest.skip("Event suppressed by noise control")
        assert result.canonical_event == expected

    @pytest.mark.parametrize(
        "oc_event",
        [
            # Real OpenCode v2 bus events that carry no display value — must be
            # dropped at the adapter so they never reach the BLE status line.
            "message.updated",
            "message.part.updated",
            "message.part.removed",
            "session.diff",
            "server.connected",
            # Anything outside the known map should also be dropped.
            "unknown.event",
            "",
        ],
    )
    def test_unknown_events_dropped(self, oc_event):
        """Adapter returns None for any provider_event not in _OC_EVENT_MAP."""
        result = adapt_opencode_event(_ev(oc_event))
        assert result is None

    def test_provider_is_always_opencode(self):
        result = adapt_opencode_event(
            _ev("tool.execute.before", tool_name="Bash", label="ls", session_id="s1")
        )
        assert result is not None
        assert result.provider == "opencode"

    def test_provider_event_preserved(self):
        result = adapt_opencode_event(_ev("tool.execute.after", tool_name="Edit"))
        assert result is not None
        assert result.provider_event == "tool.execute.after"


# ---------------------------------------------------------------------------
# ANSI stripping and whitespace normalisation
# ---------------------------------------------------------------------------


class TestCleaning:
    def test_ansi_stripped_from_label(self):
        result = adapt_opencode_event(
            _ev(
                "tool.execute.before",
                tool_name="Bash",
                label="\x1b[32mgit status\x1b[0m",
                session_id="s1",
            )
        )
        assert result is not None
        assert result.label == "git status"

    def test_control_chars_stripped(self):
        result = adapt_opencode_event(
            _ev(
                "tool.execute.before",
                tool_name="Bash",
                label="git\x00status",
                session_id="s2",
            )
        )
        assert result is not None
        assert "\x00" not in (result.label or "")

    def test_multiple_spaces_collapsed(self):
        result = adapt_opencode_event(
            _ev(
                "tool.execute.before",
                tool_name="Bash",
                label="git   status   --short",
                session_id="s3",
            )
        )
        assert result is not None
        assert result.label == "git status --short"

    def test_status_text_cleaned(self):
        result = adapt_opencode_event(
            _ev(
                "session.status",
                status_text="\x1b[1mRunning\x1b[0m  tests",
                session_id="s4",
            )
        )
        assert result is not None
        assert result.status_text == "Running tests"


# ---------------------------------------------------------------------------
# Debounce suppression
# ---------------------------------------------------------------------------


class TestDebounce:
    def test_first_event_passes(self):
        result = adapt_opencode_event(
            _ev(
                "tool.execute.before",
                tool_name="Bash",
                label="ls",
                session_id="s1",
            )
        )
        assert result is not None

    def test_rapid_duplicate_suppressed(self):
        payload = _ev(
            "tool.execute.before", tool_name="Bash", label="ls", session_id="s1"
        )
        first = adapt_opencode_event(payload)
        second = adapt_opencode_event(payload)
        assert first is not None
        assert second is None

    def test_different_session_not_suppressed(self):
        adapt_opencode_event(
            _ev("tool.execute.before", tool_name="Bash", label="ls", session_id="s1")
        )
        result = adapt_opencode_event(
            _ev("tool.execute.before", tool_name="Bash", label="ls", session_id="s2")
        )
        assert result is not None

    def test_different_label_not_suppressed(self):
        adapt_opencode_event(
            _ev("tool.execute.before", tool_name="Bash", label="ls", session_id="s1")
        )
        result = adapt_opencode_event(
            _ev("tool.execute.before", tool_name="Bash", label="pwd", session_id="s1")
        )
        assert result is not None

    def test_non_tool_events_not_debounced(self):
        """session.idle should never be debounced."""
        for _ in range(3):
            result = adapt_opencode_event(_ev("session.idle", session_id="s1"))
            assert result is not None

    def test_clear_cache_allows_resubmission(self):
        payload = _ev(
            "tool.execute.before", tool_name="Bash", label="ls", session_id="s1"
        )
        adapt_opencode_event(payload)
        clear_debounce_cache()
        result = adapt_opencode_event(payload)
        assert result is not None


# ---------------------------------------------------------------------------
# session.updated suppression
# ---------------------------------------------------------------------------


class TestSessionUpdatedSuppression:
    def test_first_session_updated_passes(self):
        result = adapt_opencode_event(
            _ev("session.updated", status_text="Running", session_id="s1")
        )
        assert result is not None

    def test_same_status_suppressed(self):
        adapt_opencode_event(
            _ev("session.updated", status_text="Running", session_id="s1")
        )
        result = adapt_opencode_event(
            _ev("session.updated", status_text="Running", session_id="s1")
        )
        assert result is None

    def test_different_status_passes(self):
        adapt_opencode_event(
            _ev("session.updated", status_text="Running", session_id="s1")
        )
        result = adapt_opencode_event(
            _ev("session.updated", status_text="Done", session_id="s1")
        )
        assert result is not None

    def test_null_status_suppressed(self):
        result = adapt_opencode_event(_ev("session.updated", session_id="s1"))
        assert result is None

    def test_different_session_not_suppressed(self):
        adapt_opencode_event(
            _ev("session.updated", status_text="Running", session_id="s1")
        )
        result = adapt_opencode_event(
            _ev("session.updated", status_text="Running", session_id="s2")
        )
        assert result is not None

    def test_clear_cache_allows_resubmission(self):
        adapt_opencode_event(
            _ev("session.updated", status_text="Running", session_id="s1")
        )
        clear_status_cache()
        result = adapt_opencode_event(
            _ev("session.updated", status_text="Running", session_id="s1")
        )
        assert result is not None


# ---------------------------------------------------------------------------
# Label extraction
# ---------------------------------------------------------------------------


class TestLabelExtraction:
    def test_explicit_label_used(self):
        result = adapt_opencode_event(
            _ev(
                "tool.execute.before",
                tool_name="Bash",
                label="git status",
                session_id="s1",
            )
        )
        assert result is not None
        assert result.label == "git status"

    def test_file_edit_label_from_path(self):
        result = adapt_opencode_event(_ev("file.edited", path="/src/app.py"))
        assert result is not None
        assert result.label == "/src/app.py"

    def test_file_edit_label_from_meta_path(self):
        result = adapt_opencode_event(_ev("file.edited", meta={"path": "/src/lib.py"}))
        assert result is not None
        assert result.label == "/src/lib.py"

    def test_command_label_from_meta(self):
        result = adapt_opencode_event(
            _ev("command.executed", meta={"command": "npm test"})
        )
        assert result is not None
        assert result.label == "npm test"

    def test_permission_asked_label_from_meta(self):
        result = adapt_opencode_event(
            _ev("permission.asked", meta={"message": "Allow file deletion?"})
        )
        assert result is not None
        assert result.label == "Allow file deletion?"

    def test_permission_replied_approved(self):
        result = adapt_opencode_event(
            _ev("permission.replied", meta={"approved": True})
        )
        assert result is not None
        assert result.label == "approved"

    def test_permission_replied_denied(self):
        result = adapt_opencode_event(
            _ev("permission.replied", meta={"approved": False})
        )
        assert result is not None
        assert result.label == "denied"

    def test_permission_replied_decision_key(self):
        result = adapt_opencode_event(
            _ev("permission.replied", meta={"decision": True})
        )
        assert result is not None
        assert result.label == "approved"

    def test_no_label_for_session_idle(self):
        result = adapt_opencode_event(_ev("session.idle", session_id="s1"))
        assert result is not None
        assert result.label is None


# ---------------------------------------------------------------------------
# Path extraction
# ---------------------------------------------------------------------------


class TestPathExtraction:
    def test_top_level_path_used(self):
        result = adapt_opencode_event(_ev("file.edited", path="/src/main.py"))
        assert result is not None
        assert result.path == "/src/main.py"

    def test_meta_path_fallback(self):
        result = adapt_opencode_event(_ev("file.edited", meta={"path": "/lib/util.py"}))
        assert result is not None
        assert result.path == "/lib/util.py"

    def test_meta_file_fallback(self):
        result = adapt_opencode_event(
            _ev("file.edited", meta={"file": "/lib/other.py"})
        )
        assert result is not None
        assert result.path == "/lib/other.py"

    def test_meta_filename_fallback(self):
        result = adapt_opencode_event(
            _ev("file.edited", meta={"filename": "config.py"})
        )
        assert result is not None
        assert result.path == "config.py"

    def test_no_path_returns_none(self):
        result = adapt_opencode_event(_ev("session.idle", session_id="s1"))
        assert result is not None
        assert result.path is None


# ---------------------------------------------------------------------------
# Timestamp and active flag
# ---------------------------------------------------------------------------


class TestTimestampAndActive:
    def test_ts_from_payload(self):
        result = adapt_opencode_event(_ev("session.created", ts=1234567890.0))
        assert result is not None
        assert result.ts == 1234567890.0

    def test_ts_defaults_to_now(self):
        before = time.time()
        result = adapt_opencode_event(_ev("session.created"))
        after = time.time()
        assert result is not None
        assert before <= result.ts <= after

    def test_active_true_by_default(self):
        result = adapt_opencode_event(
            _ev("tool.execute.before", tool_name="Bash", label="ls", session_id="s1")
        )
        assert result is not None
        assert result.active is True

    def test_active_false_when_set(self):
        result = adapt_opencode_event(_ev("session.error", active=False))
        assert result is not None
        assert result.active is False


# ---------------------------------------------------------------------------
# Meta passthrough
# ---------------------------------------------------------------------------


class TestMetaPassthrough:
    def test_meta_preserved(self):
        result = adapt_opencode_event(_ev("session.created", meta={"key": "val"}))
        assert result is not None
        assert result.meta == {"key": "val"}

    def test_empty_meta(self):
        result = adapt_opencode_event(_ev("session.created"))
        assert result is not None
        assert result.meta == {}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_payload(self):
        # An empty payload has provider_event="" which is not in _OC_EVENT_MAP
        # and is therefore dropped as unknown noise.
        result = adapt_opencode_event({})
        assert result is None

    def test_event_key_fallback(self):
        """Adapter should also accept 'event' key (not just 'provider_event')."""
        result = adapt_opencode_event({"event": "session.created"})
        assert result is not None
        assert result.canonical_event == "session_start"

    def test_session_id_none(self):
        result = adapt_opencode_event(_ev("session.created", session_id=None))
        assert result is not None
        assert result.session_id is None

    def test_tool_name_none(self):
        result = adapt_opencode_event(
            _ev("tool.execute.before", session_id="s1", label="x")
        )
        assert result is not None
        assert result.tool_name is None

    def test_large_label_not_truncated_by_adapter(self):
        """Truncation is the formatter's job, not the adapter's."""
        long_label = "a" * 500
        result = adapt_opencode_event(
            _ev(
                "tool.execute.before",
                tool_name="Bash",
                label=long_label,
                session_id="s1",
            )
        )
        assert result is not None
        assert len(result.label) == 500

"""
test_session_tracker.py — Tests for ohm.session_tracker

Coverage
--------
- Initial state: all counters zero, payload is valid JSON ≤ 100 bytes
- on_message: PreToolUse/Bash increments bash_count
- on_message: PreToolUse/Edit adds to edited_files (deduplication)
- on_message: PreToolUse/Write adds to edited_files
- on_message: PreToolUse/MultiEdit adds to edited_files
- on_message: Notification starts idle timer
- on_message: PreToolUse after Notification stops idle timer
- on_message: Stop stops idle timer and records last_completion_time
- on_message: Stop sets last_completion_time
- on_message: unknown event increments tool_calls only
- reset() clears all state
- to_ble_payload: valid UTF-8 JSON
- to_ble_payload: ≤ MAX_STATS_LEN bytes
- to_ble_payload: all expected keys present
- to_ble_payload: duration increases over time
- to_ble_payload: idle accumulates correctly
- to_ble_payload: last_completion "never" when no Stop
- to_ble_payload: last_completion "Xs ago" format
- to_ble_payload: last_completion "Xm ago" format
- to_ble_payload: c field capped at 8 chars
- Full session replay: realistic sequence of events
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ohm.session_tracker import SessionStats
from ohm.protocol import MAX_STATS_LEN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(event: str, tool_name: str = "", path: str = "", command: str = ""):
    """Build a minimal IpcMessage-like object."""
    tool_input = {}
    if path:
        tool_input["path"] = path
    if command:
        tool_input["command"] = command
    return SimpleNamespace(
        event=event,
        event_data={
            "tool_name": tool_name,
            "tool_input": tool_input,
        },
    )


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_all_counters_zero(self):
        ss = SessionStats()
        assert ss.tool_calls == 0
        assert ss.bash_count == 0
        assert len(ss.edited_files) == 0
        assert ss.idle_seconds == 0.0
        assert ss.last_completion_time is None

    def test_initial_payload_valid_json(self):
        ss = SessionStats()
        payload = ss.to_ble_payload()
        data = json.loads(payload.decode("utf-8"))
        assert isinstance(data, dict)

    def test_initial_payload_within_byte_limit(self):
        ss = SessionStats()
        assert len(ss.to_ble_payload()) <= MAX_STATS_LEN

    def test_initial_payload_all_keys(self):
        ss = SessionStats()
        data = json.loads(ss.to_ble_payload())
        for key in ("d", "t", "e", "b", "i", "c"):
            assert key in data, f"Missing key: {key}"

    def test_initial_completion_is_never(self):
        ss = SessionStats()
        data = json.loads(ss.to_ble_payload())
        assert data["c"] == "never"


# ---------------------------------------------------------------------------
# on_message — tool counting
# ---------------------------------------------------------------------------


class TestOnMessageToolCounting:
    def test_bash_increments_bash_count(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "Bash", command="ls"))
        assert ss.bash_count == 1

    def test_bash_increments_tool_calls(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "Bash", command="ls"))
        assert ss.tool_calls == 1

    def test_multiple_bash_commands(self):
        ss = SessionStats()
        for cmd in ["ls", "git status", "npm test"]:
            ss.on_message(_msg("PreToolUse", "Bash", command=cmd))
        assert ss.bash_count == 3

    def test_edit_adds_to_edited_files(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "Edit", path="/src/foo.py"))
        assert "/src/foo.py" in ss.edited_files

    def test_write_adds_to_edited_files(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "Write", path="/src/bar.py"))
        assert "/src/bar.py" in ss.edited_files

    def test_multiedit_adds_to_edited_files(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "MultiEdit", path="/src/baz.py"))
        assert "/src/baz.py" in ss.edited_files

    def test_edit_deduplication(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "Edit", path="/src/foo.py"))
        ss.on_message(_msg("PreToolUse", "Edit", path="/src/foo.py"))
        assert len(ss.edited_files) == 1

    def test_multiple_different_files(self):
        ss = SessionStats()
        for p in ["/a.py", "/b.py", "/c.py"]:
            ss.on_message(_msg("PreToolUse", "Edit", path=p))
        assert len(ss.edited_files) == 3

    def test_non_bash_non_edit_increments_tool_calls_only(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "Read", path="/x.py"))
        assert ss.tool_calls == 1
        assert ss.bash_count == 0
        assert len(ss.edited_files) == 0

    def test_post_tool_use_increments_tool_calls(self):
        ss = SessionStats()
        ss.on_message(_msg("PostToolUse", "Edit"))
        assert ss.tool_calls == 1
        assert ss.bash_count == 0

    def test_unknown_event_increments_tool_calls(self):
        ss = SessionStats()
        ss.on_message(_msg("UnknownEvent"))
        assert ss.tool_calls == 1


# ---------------------------------------------------------------------------
# on_message — idle timer
# ---------------------------------------------------------------------------


class TestIdleTimer:
    def test_notification_starts_idle_timer(self):
        ss = SessionStats()
        ss.on_message(_msg("Notification"))
        assert ss.last_idle_start is not None

    def test_pretooluse_after_notification_stops_timer(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            mock_time.return_value = 1000.0
            ss.on_message(_msg("Notification"))
            mock_time.return_value = 1045.0
            ss.on_message(_msg("PreToolUse", "Bash", command="ls"))
        assert ss.idle_seconds == pytest.approx(45.0, abs=0.1)
        assert ss.last_idle_start is None

    def test_stop_after_notification_stops_timer(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            mock_time.return_value = 2000.0
            ss.on_message(_msg("Notification"))
            mock_time.return_value = 2030.0
            ss.on_message(_msg("Stop"))
        assert ss.idle_seconds == pytest.approx(30.0, abs=0.1)

    def test_multiple_idle_periods_accumulate(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            mock_time.return_value = 0.0
            ss.on_message(_msg("Notification"))
            mock_time.return_value = 10.0
            ss.on_message(_msg("PreToolUse", "Bash", command="ls"))
            mock_time.return_value = 20.0
            ss.on_message(_msg("Notification"))
            mock_time.return_value = 35.0
            ss.on_message(_msg("PreToolUse", "Bash", command="ls"))
        assert ss.idle_seconds == pytest.approx(25.0, abs=0.1)

    def test_open_idle_window_included_in_payload(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            mock_time.return_value = 0.0
            ss.on_message(_msg("Notification"))
            mock_time.return_value = 20.0
            payload = ss.to_ble_payload()
        data = json.loads(payload)
        assert data["i"] == pytest.approx(20, abs=1)


# ---------------------------------------------------------------------------
# on_message — Stop event
# ---------------------------------------------------------------------------


class TestStopEvent:
    def test_stop_sets_last_completion_time(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            mock_time.return_value = 5000.0
            ss.on_message(_msg("Stop"))
        assert ss.last_completion_time == pytest.approx(5000.0)

    def test_stop_completion_seconds_format(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            mock_time.return_value = 1000.0
            ss.on_message(_msg("Stop"))
            mock_time.return_value = 1030.0
            payload = ss.to_ble_payload()
        data = json.loads(payload)
        assert data["c"] == "30s ago"

    def test_stop_completion_minutes_format(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            mock_time.return_value = 1000.0
            ss.on_message(_msg("Stop"))
            mock_time.return_value = 1000.0 + 180
            payload = ss.to_ble_payload()
        data = json.loads(payload)
        assert data["c"] == "3m ago"

    def test_completion_c_field_capped_at_8_chars(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            mock_time.return_value = 1000.0
            ss.on_message(_msg("Stop"))
            # 9999 minutes → "9999m ago" = 9 chars → capped to 8
            mock_time.return_value = 1000.0 + 9999 * 60
            payload = ss.to_ble_payload()
        data = json.loads(payload)
        assert len(data["c"]) <= 8


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_tool_calls(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "Bash", command="ls"))
        ss.reset()
        assert ss.tool_calls == 0

    def test_reset_clears_bash_count(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "Bash", command="ls"))
        ss.reset()
        assert ss.bash_count == 0

    def test_reset_clears_edited_files(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "Edit", path="/a.py"))
        ss.reset()
        assert len(ss.edited_files) == 0

    def test_reset_clears_idle(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            mock_time.return_value = 0.0
            ss.on_message(_msg("Notification"))
            mock_time.return_value = 30.0
            ss.on_message(_msg("PreToolUse", "Bash", command="ls"))
        ss.reset()
        assert ss.idle_seconds == 0.0

    def test_reset_clears_last_completion(self):
        ss = SessionStats()
        ss.on_message(_msg("Stop"))
        ss.reset()
        assert ss.last_completion_time is None

    def test_reset_payload_returns_to_initial(self):
        ss = SessionStats()
        ss.on_message(_msg("PreToolUse", "Bash", command="ls"))
        ss.reset()
        data = json.loads(ss.to_ble_payload())
        assert data["t"] == 0
        assert data["b"] == 0
        assert data["c"] == "never"


# ---------------------------------------------------------------------------
# to_ble_payload — byte constraints
# ---------------------------------------------------------------------------


class TestToBlePaylod:
    def test_payload_is_bytes(self):
        ss = SessionStats()
        assert isinstance(ss.to_ble_payload(), bytes)

    def test_payload_valid_utf8(self):
        ss = SessionStats()
        payload = ss.to_ble_payload()
        payload.decode("utf-8")  # must not raise

    def test_payload_within_limit(self):
        ss = SessionStats()
        # Inflate counters to stress-test length
        for i in range(100):
            ss.on_message(
                _msg("PreToolUse", "Edit", path=f"/very/long/path/to/file_{i}.py")
            )
        ss.on_message(_msg("Stop"))
        assert len(ss.to_ble_payload()) <= MAX_STATS_LEN

    def test_payload_duration_increases(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            mock_time.return_value = 0.0
            ss.start_time = 0.0
            mock_time.return_value = 120.0
            data = json.loads(ss.to_ble_payload())
        assert data["d"] == pytest.approx(120, abs=1)

    def test_payload_e_reflects_unique_files(self):
        ss = SessionStats()
        for p in ["/a.py", "/b.py", "/a.py"]:
            ss.on_message(_msg("PreToolUse", "Edit", path=p))
        data = json.loads(ss.to_ble_payload())
        assert data["e"] == 2

    def test_payload_b_reflects_bash_count(self):
        ss = SessionStats()
        for _ in range(5):
            ss.on_message(_msg("PreToolUse", "Bash", command="ls"))
        data = json.loads(ss.to_ble_payload())
        assert data["b"] == 5


# ---------------------------------------------------------------------------
# Full session replay
# ---------------------------------------------------------------------------


class TestFullSessionReplay:
    """Simulate a realistic Claude Code session and verify final stats."""

    def test_realistic_session(self):
        ss = SessionStats()
        with patch("ohm.session_tracker.time") as mock_time:
            t = 0.0
            mock_time.return_value = t
            ss.start_time = 0.0  # anchor start_time inside the mock

            # Session start
            ss.on_message(_msg("PreToolUse", "Read", path="/README.md"))
            ss.on_message(_msg("PostToolUse", "Read"))

            # Edit three files
            for path in ["/src/app.py", "/src/utils.py", "/tests/test_app.py"]:
                ss.on_message(_msg("PreToolUse", "Edit", path=path))
                ss.on_message(_msg("PostToolUse", "Edit"))

            # Run two bash commands
            ss.on_message(_msg("PreToolUse", "Bash", command="pytest"))
            ss.on_message(_msg("PostToolUse", "Bash"))
            ss.on_message(_msg("PreToolUse", "Bash", command="git commit -m 'fix'"))
            ss.on_message(_msg("PostToolUse", "Bash"))

            # Idle for 30 seconds
            t = 30.0
            mock_time.return_value = t
            ss.on_message(_msg("Notification"))
            t = 60.0
            mock_time.return_value = t
            ss.on_message(_msg("PreToolUse", "Bash", command="git push"))
            ss.on_message(_msg("PostToolUse", "Bash"))

            # Stop
            t = 90.0
            mock_time.return_value = t
            ss.on_message(_msg("Stop"))

            # Check payload 10 seconds later
            t = 100.0
            mock_time.return_value = t
            payload = ss.to_ble_payload()

        data = json.loads(payload)

        # Duration ≈ 100s
        assert data["d"] == pytest.approx(100, abs=2)
        # 3 files edited
        assert data["e"] == 3
        # 3 bash commands
        assert data["b"] == 3
        # idle ≈ 30s
        assert data["i"] == pytest.approx(30, abs=2)
        # last completion 10s ago
        assert data["c"] == "10s ago"
        # payload within byte limit
        assert len(payload) <= MAX_STATS_LEN

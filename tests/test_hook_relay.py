"""
Tests for hook_relay.py

Covers:
- Exits 0 even when the daemon is not running (socket unavailable)
- Exits 0 on malformed JSON input
- Exits 0 on empty stdin
"""

from __future__ import annotations

import json
import subprocess
import sys


# Path to hook_relay module (run as a script via subprocess to test exit code)
_HOOK_RELAY_MODULE = "ohm.hook_relay"


def _run_relay(stdin_text: str) -> subprocess.CompletedProcess:
    """Run hook_relay as a subprocess and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", _HOOK_RELAY_MODULE],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestHookRelayExitCode:
    def test_exits_zero_when_daemon_not_running(self):
        """Must exit 0 even when the BLE daemon socket is unavailable."""
        payload = json.dumps(
            {
                "event": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "npm install"},
                "session_id": "test-session",
            }
        )
        result = _run_relay(payload)
        assert result.returncode == 0, (
            f"hook_relay exited with {result.returncode}; stderr: {result.stderr!r}"
        )

    def test_exits_zero_on_empty_stdin(self):
        """Must exit 0 when stdin is empty (no event data)."""
        result = _run_relay("")
        assert result.returncode == 0

    def test_exits_zero_on_malformed_json(self):
        """Must exit 0 even when stdin contains invalid JSON."""
        result = _run_relay("{not valid json}")
        assert result.returncode == 0

    def test_exits_zero_on_unknown_event(self):
        """Must exit 0 for unknown event types."""
        payload = json.dumps({"event": "UnknownFutureEvent"})
        result = _run_relay(payload)
        assert result.returncode == 0

    def test_exits_zero_on_post_tool_use(self):
        payload = json.dumps(
            {
                "event": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {},
            }
        )
        result = _run_relay(payload)
        assert result.returncode == 0

    def test_exits_zero_on_stop_event(self):
        payload = json.dumps({"event": "Stop"})
        result = _run_relay(payload)
        assert result.returncode == 0

    def test_exits_zero_on_notification_event(self):
        payload = json.dumps({"event": "Notification"})
        result = _run_relay(payload)
        assert result.returncode == 0

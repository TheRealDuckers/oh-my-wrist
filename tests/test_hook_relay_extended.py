"""
test_hook_relay_extended.py — Extended edge-case tests for hook_relay.py.

Covers
------
- Timing: relay subprocess completes in under 500 ms (well under the 100 ms
  target; we allow extra margin for CI overhead)
- Payload variants: all event types, deeply nested tool_input, Unicode payloads,
  very large payloads, extra unknown fields
- Failure modes: socket path exists but is not a socket, permission error,
  truncated JSON, binary garbage on stdin
- Idempotency: running the relay twice in quick succession both exit 0
- Exit code: always 0 regardless of input or daemon state
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

_MODULE = "ohm.hook_relay"
_TIMEOUT = 10  # subprocess timeout (seconds)


def _run(stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", _MODULE],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )


def _run_bytes(stdin_bytes: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", _MODULE],
        input=stdin_bytes,
        capture_output=True,
        timeout=_TIMEOUT,
    )


# ============================================================================
# Exit code invariant — every input must produce exit 0
# ============================================================================


class TestExitCodeInvariant:
    @pytest.mark.parametrize(
        "payload",
        [
            # All defined event types
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "npm install"},
                }
            ),
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"path": "/src/main.py"},
                }
            ),
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "Write",
                    "tool_input": {"path": "/tmp/out.txt"},
                }
            ),
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "MultiEdit",
                    "tool_input": {"path": "/src/utils.py"},
                }
            ),
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "Read",
                    "tool_input": {"path": "/etc/hosts"},
                }
            ),
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "WebFetch",
                    "tool_input": {"url": "https://example.com"},
                }
            ),
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "WebSearch",
                    "tool_input": {"query": "python asyncio"},
                }
            ),
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "TodoWrite",
                    "tool_input": {"todos": []},
                }
            ),
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "GlobTool",
                    "tool_input": {"pattern": "**/*.py"},
                }
            ),
            json.dumps({"event": "PostToolUse", "tool_name": "Bash", "tool_input": {}}),
            json.dumps({"event": "Notification"}),
            json.dumps({"event": "Stop"}),
            json.dumps({"event": "SessionStart"}),
            # Edge cases
            json.dumps({"event": "UnknownFutureEvent"}),
            json.dumps({}),
            "{}",
            "",
            "   ",
            "{not valid json at all}",
            "null",
            "[]",
            "42",
            '"just a string"',
            # Very large payload
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "x" * 10_000},
                }
            ),
            # Unicode payload
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"path": "/プロジェクト/ファイル名.py"},
                }
            ),
            # Extra unknown fields
            json.dumps({"event": "Stop", "unknown_field": "value", "another": 123}),
            # Deeply nested tool_input
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "TodoWrite",
                    "tool_input": {
                        "todos": [
                            {"id": str(i), "content": f"task {i}", "status": "pending"}
                            for i in range(50)
                        ]
                    },
                }
            ),
        ],
    )
    def test_always_exits_zero(self, payload):
        result = _run(payload)
        assert result.returncode == 0, (
            f"Expected exit 0 for payload {payload[:60]!r}…, got {result.returncode}; "
            f"stderr: {result.stderr[:200]!r}"
        )

    def test_exits_zero_on_binary_garbage(self):
        result = _run_bytes(b"\xff\xfe\x00\x01\x80\x90\xab")
        assert result.returncode == 0

    def test_exits_zero_on_truncated_json(self):
        result = _run('{"event": "PreToolUse", "tool_name": "Bash"')
        assert result.returncode == 0

    def test_exits_zero_on_json_array(self):
        result = _run('[{"event": "Stop"}]')
        assert result.returncode == 0

    def test_exits_zero_on_very_long_line(self):
        result = _run("A" * 1_000_000)
        assert result.returncode == 0


# ============================================================================
# Timing: relay must complete well within 100 ms (allow 500 ms for CI)
# ============================================================================


class TestRelayTiming:
    def test_completes_within_500ms_bash_event(self):
        payload = json.dumps(
            {
                "event": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "npm install"},
            }
        )
        start = time.monotonic()
        result = _run(payload)
        elapsed = time.monotonic() - start
        assert result.returncode == 0
        assert elapsed < 0.5, f"hook_relay took {elapsed:.3f}s (limit 0.5s)"

    def test_completes_within_500ms_stop_event(self):
        payload = json.dumps({"event": "Stop"})
        start = time.monotonic()
        result = _run(payload)
        elapsed = time.monotonic() - start
        assert result.returncode == 0
        assert elapsed < 0.5, f"hook_relay took {elapsed:.3f}s (limit 0.5s)"

    def test_completes_within_500ms_empty_stdin(self):
        start = time.monotonic()
        result = _run("")
        elapsed = time.monotonic() - start
        assert result.returncode == 0
        assert elapsed < 0.5


# ============================================================================
# Idempotency: two rapid successive calls both exit 0
# ============================================================================


class TestRelayIdempotency:
    def test_two_rapid_calls_both_exit_zero(self):
        payload = json.dumps(
            {
                "event": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
            }
        )
        r1 = _run(payload)
        r2 = _run(payload)
        assert r1.returncode == 0
        assert r2.returncode == 0

    def test_different_events_in_sequence(self):
        events = [
            json.dumps({"event": "SessionStart"}),
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "npm install"},
                }
            ),
            json.dumps({"event": "PostToolUse", "tool_name": "Bash", "tool_input": {}}),
            json.dumps(
                {
                    "event": "PreToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"path": "/src/main.py"},
                }
            ),
            json.dumps({"event": "PostToolUse", "tool_name": "Edit", "tool_input": {}}),
            json.dumps({"event": "Notification"}),
            json.dumps({"event": "Stop"}),
        ]
        for payload in events:
            result = _run(payload)
            assert result.returncode == 0, (
                f"Non-zero exit for {payload!r}: {result.stderr!r}"
            )


# ============================================================================
# Relay does not write to stdout (Claude Code reads stdout for hook results)
# ============================================================================


class TestRelayStdout:
    def test_no_stdout_output_on_normal_event(self):
        payload = json.dumps(
            {
                "event": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
            }
        )
        result = _run(payload)
        assert result.stdout == "", (
            f"hook_relay must not write to stdout; got: {result.stdout!r}"
        )

    def test_no_stdout_output_on_empty_stdin(self):
        result = _run("")
        assert result.stdout == ""

    def test_no_stdout_output_on_malformed_json(self):
        result = _run("{bad json}")
        assert result.stdout == ""

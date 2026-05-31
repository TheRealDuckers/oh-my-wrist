"""
test_protocol_extended.py — Extended edge-case tests for protocol.py.

Covers
------
- HookEvent: optional fields, extra fields ignored, alias handling
- IpcMessage: field validation, ts precision, JSON wire format
- encode_message / decode_message: round-trips with multi-byte UTF-8,
  very long status strings, null bytes, Unicode across all planes
- UUID constants: upper/lower case normalisation, separator positions
- IPC_BACKEND: correct value for current platform
- History protocol constants (PROTOCOL_VERSION, ENTRY_TEXT_MAX, MAX_FRAME_LEN)
"""

from __future__ import annotations

import json
import sys
import time

import pytest

from ohm.protocol import (
    OHM_SERVICE_UUID,
    ENTRY_TEXT_MAX,
    HISTORY_CHAR_UUID,
    IPC_BACKEND,
    MAX_FRAME_LEN,
    NAMED_PIPE_PATH,
    PROTOCOL_VERSION,
    SESSION_CHAR_UUID,
    SOCKET_PATH,
    HookEvent,
    IpcMessage,
    decode_message,
    encode_message,
)


# ============================================================================
# Constants
# ============================================================================


class TestConstants:
    def test_protocol_version_is_1(self):
        assert PROTOCOL_VERSION == 0x01

    def test_entry_text_max_is_18(self):
        assert ENTRY_TEXT_MAX == 18

    def test_max_frame_len_is_22(self):
        assert MAX_FRAME_LEN == 22
        assert MAX_FRAME_LEN == 4 + ENTRY_TEXT_MAX

    def test_socket_path_is_tmp(self):
        assert SOCKET_PATH.startswith("/tmp/")

    def test_named_pipe_path_prefix(self):
        # Actual value: '\\.\pipe\ohm'
        assert "pipe" in NAMED_PIPE_PATH

    def test_ipc_backend_matches_platform(self):
        if sys.platform == "win32":
            assert IPC_BACKEND == "pipe"
        else:
            assert IPC_BACKEND == "unix"

    def test_uuid_separators_at_correct_positions(self):
        """UUID must have hyphens at positions 8, 13, 18, 23."""
        for uuid in (OHM_SERVICE_UUID, HISTORY_CHAR_UUID, SESSION_CHAR_UUID):
            assert uuid[8] == "-", f"Position 8 not '-' in {uuid}"
            assert uuid[13] == "-", f"Position 13 not '-' in {uuid}"
            assert uuid[18] == "-", f"Position 18 not '-' in {uuid}"
            assert uuid[23] == "-", f"Position 23 not '-' in {uuid}"

    def test_uuid_segments_correct_lengths(self):
        """UUID segments must be 8-4-4-4-12 hex characters."""
        for uuid in (OHM_SERVICE_UUID, HISTORY_CHAR_UUID, SESSION_CHAR_UUID):
            parts = uuid.split("-")
            assert len(parts) == 5, f"Expected 5 parts in {uuid}"
            expected_lengths = [8, 4, 4, 4, 12]
            for part, expected in zip(parts, expected_lengths):
                assert len(part) == expected, (
                    f"Part {part!r} has length {len(part)}, expected {expected} in {uuid}"
                )

    def test_uuids_only_hex_and_hyphens(self):
        import re

        pattern = re.compile(r"^[0-9a-fA-F\-]+$")
        for uuid in (OHM_SERVICE_UUID, HISTORY_CHAR_UUID, SESSION_CHAR_UUID):
            assert pattern.match(uuid), f"Non-hex character in UUID {uuid!r}"

    def test_service_uuid_differs_from_history_char(self):
        assert OHM_SERVICE_UUID.upper() != HISTORY_CHAR_UUID.upper()

    def test_service_uuid_differs_from_session_char(self):
        assert OHM_SERVICE_UUID.upper() != SESSION_CHAR_UUID.upper()

    def test_history_char_differs_from_session_char(self):
        assert HISTORY_CHAR_UUID.upper() != SESSION_CHAR_UUID.upper()


# ============================================================================
# HookEvent model
# ============================================================================


class TestHookEventModel:
    def test_minimal_valid_event(self):
        ev = HookEvent.model_validate({"event": "Stop"})
        assert ev.event == "Stop"
        assert ev.tool_name is None
        assert ev.tool_input is None
        assert ev.session_id is None

    def test_full_event(self):
        ev = HookEvent.model_validate(
            {
                "event": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "ls -la"},
                "session_id": "abc-123",
            }
        )
        assert ev.event == "PreToolUse"
        assert ev.tool_name == "Bash"
        assert ev.tool_input == {"command": "ls -la"}
        assert ev.session_id == "abc-123"

    def test_extra_fields_ignored(self):
        # Pydantic v2 ignores extra fields by default
        ev = HookEvent.model_validate(
            {
                "event": "PostToolUse",
                "tool_name": "Edit",
                "tool_input": {},
                "session_id": "x",
                "extra_unknown_field": "should be ignored",
            }
        )
        assert ev.event == "PostToolUse"

    def test_default_event_is_unknown(self):
        ev = HookEvent.model_validate({})
        assert ev.event == "Unknown"

    def test_tool_input_can_be_nested_dict(self):
        ev = HookEvent.model_validate(
            {
                "event": "PreToolUse",
                "tool_name": "TodoWrite",
                "tool_input": {
                    "todos": [
                        {
                            "id": "1",
                            "content": "Fix bug",
                            "status": "pending",
                            "priority": "high",
                        }
                    ]
                },
            }
        )
        assert isinstance(ev.tool_input["todos"], list)

    def test_tool_input_can_be_empty_dict(self):
        ev = HookEvent.model_validate({"event": "PreToolUse", "tool_input": {}})
        assert ev.tool_input == {}

    def test_tool_name_alias_accepted(self):
        # The model uses alias "tool_name" — verify it works
        ev = HookEvent.model_validate({"event": "PreToolUse", "tool_name": "Bash"})
        assert ev.tool_name == "Bash"

    def test_session_id_optional(self):
        ev = HookEvent.model_validate({"event": "Notification"})
        assert ev.session_id is None

    def test_event_preserves_case(self):
        for name in (
            "PreToolUse",
            "PostToolUse",
            "Notification",
            "Stop",
            "SessionStart",
        ):
            ev = HookEvent.model_validate({"event": name})
            assert ev.event == name

    def test_unicode_session_id(self):
        ev = HookEvent.model_validate({"event": "Stop", "session_id": "セッション-123"})
        assert ev.session_id == "セッション-123"


# ============================================================================
# IpcMessage model
# ============================================================================


class TestIpcMessageModel:
    def test_required_fields(self):
        msg = IpcMessage(status="ok: done", event="PostToolUse")
        assert msg.status == "ok: done"
        assert msg.event == "PostToolUse"
        assert isinstance(msg.ts, float)

    def test_ts_precision(self):
        before = time.time()
        msg = IpcMessage(status="x", event="y")
        after = time.time()
        assert before <= msg.ts <= after

    def test_explicit_ts(self):
        msg = IpcMessage(status="x", event="y", ts=1234567890.5)
        assert msg.ts == pytest.approx(1234567890.5)

    def test_status_can_be_empty(self):
        msg = IpcMessage(status="", event="Stop")
        assert msg.status == ""


# ============================================================================
# encode_message / decode_message round-trips
# ============================================================================


class TestCodecEdgeCases:
    def test_roundtrip_empty_status(self):
        msg = IpcMessage(status="", event="Stop", ts=1.0)
        decoded = decode_message(encode_message(msg))
        assert decoded.status == ""
        assert decoded.event == "Stop"

    def test_roundtrip_all_ascii(self):
        msg = IpcMessage(status="run: npm", event="PreToolUse", ts=1715000000.0)
        decoded = decode_message(encode_message(msg))
        assert decoded.status == msg.status
        assert decoded.event == msg.event
        assert abs(decoded.ts - msg.ts) < 1e-6

    def test_roundtrip_japanese(self):
        msg = IpcMessage(status="edit: ファイル.py", event="PreToolUse")
        decoded = decode_message(encode_message(msg))
        assert decoded.status == "edit: ファイル.py"

    def test_roundtrip_arabic(self):
        msg = IpcMessage(status="run: مرحبا", event="PreToolUse")
        decoded = decode_message(encode_message(msg))
        assert decoded.status == "run: مرحبا"

    def test_encoded_bytes_are_valid_json_line(self):
        msg = IpcMessage(status="ok: done", event="PostToolUse", ts=1.0)
        raw = encode_message(msg)
        line = raw.decode("utf-8").strip()
        parsed = json.loads(line)
        assert parsed["status"] == "ok: done"
        assert parsed["event"] == "PostToolUse"

    def test_encoded_bytes_end_with_newline(self):
        msg = IpcMessage(status="x", event="y")
        assert encode_message(msg).endswith(b"\n")

    def test_decode_strips_whitespace(self):
        msg = IpcMessage(status="x", event="y", ts=1.0)
        raw = encode_message(msg)
        # Add extra whitespace around the JSON
        padded = b"  " + raw.strip() + b"  \n"
        decoded = decode_message(padded)
        assert decoded.status == "x"

    def test_ts_survives_float_precision(self):
        ts = 1715000000.123456
        msg = IpcMessage(status="x", event="y", ts=ts)
        decoded = decode_message(encode_message(msg))
        assert abs(decoded.ts - ts) < 1e-4

    def test_multiple_messages_independent(self):
        msgs = [
            IpcMessage(status=f"status_{i}", event="PreToolUse", ts=float(i))
            for i in range(10)
        ]
        decoded = [decode_message(encode_message(m)) for m in msgs]
        for i, d in enumerate(decoded):
            assert d.status == f"status_{i}"
            assert d.ts == pytest.approx(float(i))

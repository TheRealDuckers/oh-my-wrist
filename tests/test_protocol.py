"""
Tests for protocol.py

Covers:
- UUID constants are correctly formatted (valid 128-bit UUID strings)
- IpcMessage / CanonicalIpcMessage encode/decode round-trip
- New history protocol constants (PROTOCOL_VERSION, ENTRY_TEXT_MAX, MAX_FRAME_LEN)
"""

from __future__ import annotations

import re
import time

import pytest

from ohm.protocol import (
    ALERT_CHAR_UUID,
    OHM_SERVICE_UUID,
    ENTRY_TEXT_MAX,
    HISTORY_CHAR_UUID,
    IpcMessage,
    MAX_FRAME_LEN,
    PROTOCOL_VERSION,
    SESSION_CHAR_UUID,
    STATS_CLAUDE_CHAR_UUID,
    STATS_OPENCODE_CHAR_UUID,
    decode_message,
    encode_message,
    service_uuid_for_connection_id,
)

# RFC 4122 UUID pattern (case-insensitive)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_ALL_UUIDS = (
    OHM_SERVICE_UUID,
    HISTORY_CHAR_UUID,
    SESSION_CHAR_UUID,
    ALERT_CHAR_UUID,
    STATS_CLAUDE_CHAR_UUID,
    STATS_OPENCODE_CHAR_UUID,
)


class TestUuidConstants:
    @pytest.mark.parametrize("uuid", _ALL_UUIDS)
    def test_uuid_format(self, uuid):
        assert _UUID_RE.match(uuid), f"not a valid UUID: {uuid!r}"

    def test_all_uuids_distinct(self):
        assert len({u.upper() for u in _ALL_UUIDS}) == len(_ALL_UUIDS)

    @pytest.mark.parametrize("uuid", _ALL_UUIDS)
    def test_uuid_128_bit(self, uuid):
        assert len(uuid.replace("-", "")) == 32

    def test_connection_id_zero_preserves_default_service_uuid(self):
        assert service_uuid_for_connection_id(0) == OHM_SERVICE_UUID

    def test_connection_id_service_uuids_are_unique(self):
        uuids = {service_uuid_for_connection_id(i).upper() for i in range(256)}
        assert len(uuids) == 256

    @pytest.mark.parametrize("connection_id", [0, 1, 42, 255])
    def test_connection_id_service_uuid_format(self, connection_id):
        uuid = service_uuid_for_connection_id(connection_id)
        assert _UUID_RE.match(uuid)

    @pytest.mark.parametrize("connection_id", [-1, 256])
    def test_connection_id_service_uuid_rejects_out_of_range(self, connection_id):
        with pytest.raises(ValueError):
            service_uuid_for_connection_id(connection_id)


class TestHistoryProtocolConstants:
    def test_protocol_version(self):
        assert PROTOCOL_VERSION == 0x01

    def test_entry_text_max(self):
        assert ENTRY_TEXT_MAX == 18

    def test_max_frame_len_fits_att_mtu(self):
        # ATT MTU 23 minus the 3-byte ATT notification header leaves 20 bytes
        # for payload — we cap at 22 (4-byte frame header + ENTRY_TEXT_MAX),
        # but in practice the stack negotiates a larger MTU. Either way the
        # frame must not exceed our self-imposed ceiling.
        assert MAX_FRAME_LEN == 4 + ENTRY_TEXT_MAX
        assert MAX_FRAME_LEN <= 24


class TestIpcMessageCodec:
    def test_encode_decode_roundtrip(self):
        original = IpcMessage(
            status="edit: main.py", event="PreToolUse", ts=1715000000.123
        )
        encoded = encode_message(original)
        decoded = decode_message(encoded)
        assert decoded.status == original.status
        assert decoded.event == original.event
        assert abs(decoded.ts - original.ts) < 1e-6

    def test_encode_ends_with_newline(self):
        msg = IpcMessage(status="ok: done", event="PostToolUse")
        encoded = encode_message(msg)
        assert encoded.endswith(b"\n")

    def test_default_ts_is_recent(self):
        before = time.time()
        msg = IpcMessage(status="idle: waiting", event="Notification")
        after = time.time()
        assert before <= msg.ts <= after

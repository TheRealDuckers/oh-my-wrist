"""
Tests for the USAGE characteristic path in ble_daemon.py

Covers:
- A usage CanonicalIpcMessage updates usage state and enqueues a USAGE notify.
- Identical usage payloads are suppressed (no redundant notify).
- A usage message does NOT produce a history frame.
- Absent windows default to -1.
- A non-claude usage message is ignored.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ohm.protocol import USAGE_CHAR_UUID, CanonicalIpcMessage


def _make_daemon():
    mock_server = MagicMock()
    mock_char = MagicMock()
    mock_char.value = bytearray()
    mock_server.get_characteristic.return_value = mock_char

    with patch("ohm.ble_daemon.BlessServer", return_value=mock_server):
        from ohm.ble_daemon import BleDaemon

        daemon = BleDaemon()
        daemon._server = mock_server
        daemon._device_connected = True
        daemon._has_subscribers = True
        return daemon, mock_server, mock_char


def _usage_msg(provider="claude", s=23, w=41):
    return CanonicalIpcMessage(
        provider=provider,
        provider_event="statusline",
        canonical_event="usage",
        meta={"s": s, "w": w},
    )


class TestUsageIngestion:
    def test_usage_message_updates_state_and_notifies(self):
        daemon, _, _ = _make_daemon()
        daemon._process_ipc_message(_usage_msg(s=23, w=41))
        assert daemon._usage == {"s": 23, "w": 41}
        service_uuid, char_uuid = daemon._notify_queue.get_nowait()
        assert char_uuid == USAGE_CHAR_UUID

    def test_usage_message_does_not_create_history_frame(self):
        daemon, _, _ = _make_daemon()
        daemon._process_ipc_message(_usage_msg())
        assert daemon._last_frame == b""

    def test_identical_payload_suppressed(self):
        daemon, _, _ = _make_daemon()
        daemon._process_ipc_message(_usage_msg(s=10, w=20))
        daemon._notify_queue.get_nowait()  # drain first notify
        daemon._process_ipc_message(_usage_msg(s=10, w=20))
        assert daemon._notify_queue.empty()

    def test_absent_windows_default_to_minus_one(self):
        daemon, _, _ = _make_daemon()
        msg = CanonicalIpcMessage(
            provider="claude",
            provider_event="statusline",
            canonical_event="usage",
            meta={},
        )
        daemon._process_ipc_message(msg)
        assert daemon._usage == {"s": -1, "w": -1}

    def test_non_claude_usage_ignored(self):
        daemon, _, _ = _make_daemon()
        daemon._process_ipc_message(_usage_msg(provider="opencode"))
        assert daemon._usage == {"s": -1, "w": -1}
        assert daemon._notify_queue.empty()

    def test_usage_payload_is_compact_json(self):
        daemon, _, _ = _make_daemon()
        daemon._usage = {"s": 5, "w": 99}
        assert daemon._usage_payload() == b'{"s":5,"w":99}'

    def test_out_of_range_values_are_clamped(self):
        daemon, _, _ = _make_daemon()
        daemon._process_ipc_message(_usage_msg(s=150, w=-5))
        assert daemon._usage == {"s": 100, "w": -1}

    def test_non_numeric_values_become_minus_one(self):
        daemon, _, _ = _make_daemon()
        daemon._process_ipc_message(_usage_msg(s="abc", w=None))
        assert daemon._usage == {"s": -1, "w": -1}

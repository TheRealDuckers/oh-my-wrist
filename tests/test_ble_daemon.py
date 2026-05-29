"""
Tests for ble_daemon.py

Covers:
- Mock BLE peripheral: HISTORY_CHAR is updated and notified on every event
- Session characteristic reflects active/idle state
- _push_event respects MAX_FRAME_LEN
- _last_frame caches the most recent encoded event
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from ohm.icons import FLAG_SPINNER, IconId
from ohm.protocol import (
    OHM_SERVICE_UUID,
    HISTORY_CHAR_UUID,
    MAX_FRAME_LEN,
    PROTOCOL_VERSION,
)
from ohm.provider_types import CanonicalEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_daemon():
    """Return a BleDaemon instance with a mocked BlessServer."""
    mock_server = MagicMock()
    mock_char = MagicMock()
    mock_char.value = bytearray()
    mock_server.get_characteristic.return_value = mock_char
    mock_server.update_value = MagicMock()

    with patch("ohm.ble_daemon.BlessServer", return_value=mock_server):
        from ohm.ble_daemon import BleDaemon

        daemon = BleDaemon()
        daemon._server = mock_server
        daemon._device_connected = True
        daemon._has_subscribers = True
        return daemon, mock_server, mock_char


def _ev(canonical: str, **kwargs) -> CanonicalEvent:
    base = {"provider": "claude", "canonical_event": canonical}
    base.update(kwargs)
    return CanonicalEvent(**base)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPushEvent:
    def test_history_characteristic_updated(self):
        daemon, mock_server, _ = _make_daemon()
        daemon._push_event(_ev("tool_start", tool_name="Bash", label="pytest"))
        # Notification should be enqueued (not called directly on server)
        assert not daemon._notify_queue.empty()
        service_uuid, char_uuid = daemon._notify_queue.get_nowait()
        assert service_uuid == OHM_SERVICE_UUID
        assert char_uuid == HISTORY_CHAR_UUID

    def test_last_frame_caches_encoded_bytes(self):
        daemon, _, _ = _make_daemon()
        daemon._push_event(_ev("tool_end"))
        assert daemon._last_frame[0] == PROTOCOL_VERSION
        assert daemon._last_frame[1] == int(IconId.CHECK)

    def test_frame_under_max_len(self):
        daemon, _, _ = _make_daemon()
        daemon._push_event(
            _ev(
                "tool_start",
                tool_name="Edit",
                path="/a/very/long/path/with/many/segments/main.py",
            )
        )
        assert len(daemon._last_frame) <= MAX_FRAME_LEN

    def test_tool_start_sets_spinner_flag(self):
        daemon, _, _ = _make_daemon()
        daemon._push_event(_ev("tool_start", tool_name="Bash", label="pytest"))
        # flags byte is at index 2
        assert daemon._last_frame[2] & FLAG_SPINNER

    def test_session_active_flag_set(self):
        daemon, _, _ = _make_daemon()
        daemon._push_event(
            _ev("tool_start", tool_name="Bash", label="pytest"), session_active=True
        )
        assert daemon._session_active == b"\x01"

    def test_session_active_flag_cleared(self):
        daemon, _, _ = _make_daemon()
        daemon._push_event(_ev("session_stop"), session_active=False)
        assert daemon._session_active == b"\x00"

    def test_no_crash_when_server_is_none(self):
        daemon, _, _ = _make_daemon()
        daemon._server = None
        daemon._push_event(_ev("tool_end"))  # must not raise

    def test_frame_valid_for_every_canonical_event(self):
        """Every supported canonical_event must produce a frame ≤ MAX_FRAME_LEN."""
        daemon, _, _ = _make_daemon()
        for ce in (
            "tool_start",
            "tool_end",
            "session_start",
            "session_idle",
            "session_stop",
            "session_error",
            "file_edit",
            "todo_update",
            "permission_request",
            "permission_reply",
            "command",
            "status",
        ):
            daemon._push_event(_ev(ce, tool_name="Bash", label="x"))
            assert len(daemon._last_frame) <= MAX_FRAME_LEN
            daemon._last_frame[4:].decode("utf-8")  # valid UTF-8 in text section


class TestNotifyHistory:
    def test_notify_re_pushes_last_frame(self):
        daemon, mock_server, _ = _make_daemon()
        daemon._push_event(_ev("tool_end"))
        # Drain the queue from _push_event
        while not daemon._notify_queue.empty():
            daemon._notify_queue.get_nowait()
        daemon._notify_history()
        assert not daemon._notify_queue.empty()
        service_uuid, char_uuid = daemon._notify_queue.get_nowait()
        assert char_uuid == HISTORY_CHAR_UUID

    def test_notify_noop_when_no_frame_yet(self):
        daemon, mock_server, _ = _make_daemon()
        daemon._notify_history()
        assert daemon._notify_queue.empty()


class TestHandleWriteSubscribe:
    def test_cccd_subscribe_repushes_history_and_stats(self):
        daemon, mock_server, _ = _make_daemon()
        daemon._push_event(_ev("tool_end"))
        # Drain the queue from _push_event
        while not daemon._notify_queue.empty():
            daemon._notify_queue.get_nowait()
        char = MagicMock()
        char.uuid = HISTORY_CHAR_UUID
        # New design: subscribe schedules a deferred push (1.5s), not an
        # immediate enqueue.  Verify the deferred handle is armed.
        with patch("ohm.ble_daemon.asyncio") as mock_asyncio:
            mock_loop = MagicMock()
            mock_asyncio.get_event_loop.return_value = mock_loop
            daemon._handle_write(char, b"\x01\x00")
        assert daemon._deferred_push_handle is not None or mock_loop.call_later.called

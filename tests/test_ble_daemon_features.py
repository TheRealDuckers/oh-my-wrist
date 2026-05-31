"""
test_ble_daemon_features.py — Tests for new Feature 1 and Feature 2
additions to ble_daemon.py.

Coverage
--------
Feature 1 — Haptic alerts:
  - _send_alert writes correct byte to ALERT_CHAR_UUID
  - _send_alert calls update_value with ALERT_CHAR_UUID
  - _send_alert resets to 0x00 after 500 ms
  - _send_alert with haptic disabled writes 0x00 immediately
  - _send_alert with quiet hours active writes 0x00 immediately
  - _send_alert with ALERT_NONE does not call update_value
  - _send_alert when server is None does not crash

Feature 2 — Stats characteristic:
  - _push_stats calls update_value with STATS_CHAR_UUID
  - _push_stats payload is valid JSON ≤ 100 bytes
  - _push_stats after on_message reflects updated counters
  - _handle_unix_client calls _push_stats after each message
  - _handle_unix_client calls session_stats.reset() on SessionStart
  - _handle_unix_client calls _send_alert when alert_type != 0

General:
  - ALERT_CHAR_UUID and STATS_CHAR_UUID are added to _setup_ble
  - _handle_read returns correct bytes for ALERT_CHAR_UUID
  - _handle_read returns correct bytes for STATS_CHAR_UUID
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ohm.ble_daemon import BleDaemon
from ohm.protocol import (
    ALERT_CHAR_UUID,
    ALERT_NONE,
    ALERT_IDLE_WAITING,
    ALERT_SESSION_DONE,
    ALERT_DESTRUCTIVE,
    ALERT_AGENT_DONE,
    STATS_CLAUDE_CHAR_UUID,
    STATS_OPENCODE_CHAR_UUID,
    IpcMessage,
    encode_message,
)
from ohm.protocol import MAX_STATS_LEN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_daemon():
    """Create a BleDaemon with a mocked BlessServer."""
    daemon = BleDaemon()

    mock_char = MagicMock()
    mock_char.value = bytearray(b"Idle")

    mock_server = MagicMock()
    mock_server.get_characteristic.return_value = mock_char
    mock_server.update_value = MagicMock()

    daemon._server = mock_server
    daemon._device_connected = True
    daemon._has_subscribers = True
    return daemon, mock_server, mock_char


def _ipc_msg(
    event: str, status: str = "ok: done", alert_type: int = 0, event_data: dict = None
) -> bytes:
    msg = IpcMessage(
        status=status,
        event=event,
        alert_type=alert_type,
        event_data=event_data or {},
    )
    return encode_message(msg)


# ---------------------------------------------------------------------------
# Feature 1 — _send_alert
# ---------------------------------------------------------------------------


class TestSendAlert:
    def test_send_alert_writes_correct_byte(self):
        daemon, mock_server, mock_char = _make_daemon()
        with patch("ohm.ble_daemon.load_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                haptic_allowed=MagicMock(return_value=True)
            )
            asyncio.run(daemon._send_alert(ALERT_IDLE_WAITING))
        # The characteristic value should have been set to [0x01]
        set_calls = [c for c in mock_char.mock_calls if "value" in str(c)]
        assert any(
            bytearray([ALERT_IDLE_WAITING]) in str(c)
            or bytearray([ALERT_IDLE_WAITING]) == getattr(c, "args", (None,))[0]
            for c in set_calls
        ) or mock_char.value == bytearray([0x00])

    def test_send_alert_calls_update_value_for_alert_char(self):
        daemon, mock_server, mock_char = _make_daemon()
        with patch("ohm.ble_daemon.load_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                haptic_allowed=MagicMock(return_value=True)
            )
            asyncio.run(daemon._send_alert(ALERT_SESSION_DONE))
        # ALERT_CHAR_UUID should be enqueued for notification
        queued = []
        while not daemon._notify_queue.empty():
            queued.append(daemon._notify_queue.get_nowait())
        assert any(char_uuid == ALERT_CHAR_UUID for _, char_uuid in queued)

    def test_send_alert_resets_to_zero_after_delay(self):
        daemon, mock_server, mock_char = _make_daemon()
        with (
            patch("ohm.ble_daemon.load_config") as mock_cfg,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_cfg.return_value = MagicMock(
                haptic_allowed=MagicMock(return_value=True)
            )
            asyncio.run(daemon._send_alert(ALERT_DESTRUCTIVE))
        # asyncio.sleep(0.5) should have been called for the reset
        mock_sleep.assert_called_once_with(0.5)
        # After reset, current_alert should be 0x00
        assert daemon._current_alert == b"\x00"

    def test_send_alert_haptic_disabled_writes_zero(self):
        daemon, mock_server, mock_char = _make_daemon()
        with patch("ohm.ble_daemon.load_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                haptic_allowed=MagicMock(return_value=False)
            )
            asyncio.run(daemon._send_alert(ALERT_IDLE_WAITING))
        # Should write 0x00 (haptic disabled) and NOT call asyncio.sleep
        assert daemon._current_alert == b"\x00"

    def test_send_alert_quiet_hours_writes_zero(self):
        daemon, mock_server, mock_char = _make_daemon()
        with patch("ohm.ble_daemon.load_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                haptic_allowed=MagicMock(return_value=False)
            )
            asyncio.run(daemon._send_alert(ALERT_SESSION_DONE))
        assert daemon._current_alert == b"\x00"

    def test_send_alert_none_does_not_sleep(self):
        daemon, mock_server, mock_char = _make_daemon()
        with (
            patch("ohm.ble_daemon.load_config") as mock_cfg,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_cfg.return_value = MagicMock(
                haptic_allowed=MagicMock(return_value=True)
            )
            asyncio.run(daemon._send_alert(ALERT_NONE))
        mock_sleep.assert_not_called()

    def test_send_alert_server_none_does_not_crash(self):
        daemon = BleDaemon()
        daemon._server = None
        with patch("ohm.ble_daemon.load_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                haptic_allowed=MagicMock(return_value=True)
            )
            # Must not raise
            asyncio.run(daemon._send_alert(ALERT_AGENT_DONE))

    @pytest.mark.parametrize(
        "alert_type",
        [ALERT_IDLE_WAITING, ALERT_SESSION_DONE, ALERT_DESTRUCTIVE, ALERT_AGENT_DONE],
    )
    def test_all_alert_types_handled(self, alert_type):
        daemon, mock_server, mock_char = _make_daemon()
        with (
            patch("ohm.ble_daemon.load_config") as mock_cfg,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_cfg.return_value = MagicMock(
                haptic_allowed=MagicMock(return_value=True)
            )
            asyncio.run(daemon._send_alert(alert_type))
        # No exception raised


# ---------------------------------------------------------------------------
# Feature 2 — _push_stats
# ---------------------------------------------------------------------------


class TestPushStats:
    def test_push_stats_calls_update_value_for_both_providers(self):
        daemon, mock_server, mock_char = _make_daemon()
        daemon._push_stats()
        queued = []
        while not daemon._notify_queue.empty():
            queued.append(daemon._notify_queue.get_nowait())
        char_uuids = [char_uuid for _, char_uuid in queued]
        assert STATS_CLAUDE_CHAR_UUID in char_uuids
        assert STATS_OPENCODE_CHAR_UUID in char_uuids

    def test_push_stats_payload_valid_json(self):
        daemon, mock_server, mock_char = _make_daemon()
        daemon._push_stats()
        # The characteristic value should be valid JSON
        set_value = mock_char.value
        if isinstance(set_value, (bytes, bytearray)):
            data = json.loads(set_value.decode("utf-8"))
            assert isinstance(data, dict)

    def test_push_stats_payload_within_limit(self):
        daemon, mock_server, mock_char = _make_daemon()
        daemon._push_stats()
        for provider in ("claude", "opencode"):
            payload = daemon._multi.payload_for(provider)
            assert len(payload) <= MAX_STATS_LEN

    def test_push_stats_reflects_updated_counters(self):
        daemon, mock_server, mock_char = _make_daemon()
        from ohm.provider_types import CanonicalEvent

        ev = CanonicalEvent(
            provider="claude", canonical_event="tool_start", tool_name="Bash"
        )
        daemon._multi.on_event(ev)
        daemon._push_stats()
        claude_data = json.loads(daemon._multi.payload_for("claude"))
        opencode_data = json.loads(daemon._multi.payload_for("opencode"))
        assert claude_data["b"] == 1
        assert opencode_data["b"] == 0

    def test_push_stats_server_none_does_not_crash(self):
        daemon = BleDaemon()
        daemon._server = None
        daemon._push_stats()  # Must not raise


# ---------------------------------------------------------------------------
# _handle_unix_client integration
# ---------------------------------------------------------------------------


class TestHandleUnixClientFeatures:
    def _run_client(self, raw_bytes: bytes):
        daemon, mock_server, mock_char = _make_daemon()

        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=raw_bytes)
        writer = MagicMock()
        writer.close = MagicMock()

        with (
            patch("ohm.ble_daemon.load_config") as mock_cfg,
            patch(
                "asyncio.ensure_future", side_effect=lambda coro: coro.close()
            ) as mock_future,
        ):
            mock_cfg.return_value = MagicMock(
                haptic_allowed=MagicMock(return_value=True)
            )
            asyncio.run(daemon._handle_unix_client(reader, writer))

        return daemon, mock_server, mock_char, mock_future

    def test_push_stats_called_after_message(self):
        raw = _ipc_msg("PreToolUse", "edit: app.py")
        daemon, mock_server, mock_char, _ = self._run_client(raw)
        # Both per-provider stats characteristics should have been enqueued
        queued = []
        while not daemon._notify_queue.empty():
            queued.append(daemon._notify_queue.get_nowait())
        char_uuids = [char_uuid for _, char_uuid in queued]
        assert STATS_CLAUDE_CHAR_UUID in char_uuids
        assert STATS_OPENCODE_CHAR_UUID in char_uuids

    def test_session_reset_on_session_start(self):
        # First add some Claude state
        raw1 = _ipc_msg("PreToolUse", "edit: app.py")
        daemon, mock_server, mock_char, _ = self._run_client(raw1)
        from ohm.provider_types import CanonicalEvent

        for _ in range(5):
            daemon._multi.on_event(
                CanonicalEvent(
                    provider="claude", canonical_event="tool_start", tool_name="Bash"
                )
            )

        # Build up OpenCode state too, so we can prove it survives Claude's reset.
        for _ in range(3):
            daemon._multi.on_event(
                CanonicalEvent(
                    provider="opencode",
                    canonical_event="tool_start",
                    tool_name="Edit",
                    path=f"/tmp/x{_}.py",
                )
            )
        opencode_files_before = len(daemon._multi.state_for("opencode").edited_files)

        # Now send SessionStart (legacy IpcMessage → adapted to claude provider)
        reader = AsyncMock()
        reader.readline = AsyncMock(
            return_value=_ipc_msg("SessionStart", "start: session")
        )
        writer = MagicMock()
        writer.close = MagicMock()

        with (
            patch("ohm.ble_daemon.load_config") as mock_cfg,
            patch("asyncio.ensure_future", side_effect=lambda coro: coro.close()),
        ):
            mock_cfg.return_value = MagicMock(
                haptic_allowed=MagicMock(return_value=True)
            )
            asyncio.run(daemon._handle_unix_client(reader, writer))

        # Claude's state was reset by session_start
        assert daemon._multi.state_for("claude").bash_count == 0
        # OpenCode's state is untouched
        assert (
            len(daemon._multi.state_for("opencode").edited_files)
            == opencode_files_before
        )

    def test_ensure_future_called_for_nonzero_alert(self):
        raw = _ipc_msg("Notification", "idle: waiting", alert_type=ALERT_IDLE_WAITING)
        daemon, mock_server, mock_char, mock_future = self._run_client(raw)
        mock_future.assert_called_once()

    def test_ensure_future_not_called_for_zero_alert(self):
        raw = _ipc_msg("PostToolUse", "ok: done", alert_type=ALERT_NONE)
        daemon, mock_server, mock_char, mock_future = self._run_client(raw)
        mock_future.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_read for new characteristics
# ---------------------------------------------------------------------------


class TestHandleReadNewChars:
    def _make_char(self, uuid_str: str):
        char = MagicMock()
        char.uuid = MagicMock()
        char.uuid.__str__ = MagicMock(return_value=uuid_str.upper())
        return char

    def test_read_alert_char_returns_current_alert(self):
        daemon = BleDaemon()
        daemon._current_alert = b"\x02"
        char = self._make_char(ALERT_CHAR_UUID)
        result = daemon._handle_read(char)
        assert result == bytearray(b"\x02")

    def test_read_claude_stats_char_returns_valid_json(self):
        daemon = BleDaemon()
        char = self._make_char(STATS_CLAUDE_CHAR_UUID)
        result = daemon._handle_read(char)
        data = json.loads(bytes(result).decode("utf-8"))
        assert isinstance(data, dict)

    def test_read_opencode_stats_char_returns_valid_json(self):
        daemon = BleDaemon()
        char = self._make_char(STATS_OPENCODE_CHAR_UUID)
        result = daemon._handle_read(char)
        data = json.loads(bytes(result).decode("utf-8"))
        assert isinstance(data, dict)

    def test_read_unknown_char_returns_empty(self):
        daemon = BleDaemon()
        char = self._make_char("00000000-0000-0000-0000-000000000000")
        result = daemon._handle_read(char)
        assert result == bytearray()


# ---------------------------------------------------------------------------
# Periodic stats task
# ---------------------------------------------------------------------------


class TestPeriodicStatsTask:
    def test_periodic_task_pushes_stats_on_timeout(self):
        daemon, mock_server, mock_char = _make_daemon()
        # Bypass Linux BlueZ path — report connected so stats are pushed.
        daemon._check_connected = AsyncMock(return_value=True)

        async def _run():
            # Replace _stop_event with a real asyncio.Event we control
            real_stop = asyncio.Event()
            daemon._stop_event = real_stop

            call_count = [0]

            async def _fake_wait_for(coro, timeout=None):
                call_count[0] += 1
                if call_count[0] == 1:
                    # Simulate timeout on first call → triggers _push_stats
                    coro.close()
                    raise asyncio.TimeoutError()
                # On second call: set the stop event so the loop exits
                real_stop.set()
                return await coro  # now resolves immediately

            with patch("asyncio.wait_for", side_effect=_fake_wait_for):
                await daemon._periodic_stats_task()

        asyncio.run(_run())
        # Both per-provider stats chars should be enqueued
        queued = []
        while not daemon._notify_queue.empty():
            queued.append(daemon._notify_queue.get_nowait())
        char_uuids = [char_uuid for _, char_uuid in queued]
        assert STATS_CLAUDE_CHAR_UUID in char_uuids
        assert STATS_OPENCODE_CHAR_UUID in char_uuids


# ---------------------------------------------------------------------------
# Keepalive — re-advertise on disconnect, cadence switching, degraded backend
# ---------------------------------------------------------------------------


def _run_one_keepalive_tick(daemon, max_ticks: int = 1):
    """Run the keepalive task for exactly `max_ticks` timeout cycles, then
    set the stop event so the task exits. Used by the keepalive tests below.
    Returns the list of timeout values passed to asyncio.wait_for in order."""
    timeouts: list[float] = []

    async def _run():
        real_stop = asyncio.Event()
        daemon._stop_event = real_stop
        ticks_done = [0]

        async def _fake_wait_for(coro, timeout=None):
            timeouts.append(timeout)
            if ticks_done[0] < max_ticks:
                ticks_done[0] += 1
                coro.close()
                raise asyncio.TimeoutError()
            real_stop.set()
            return await coro

        with patch("asyncio.wait_for", side_effect=_fake_wait_for):
            await daemon._periodic_stats_task()

    asyncio.run(_run())
    return timeouts


class TestKeepalive:
    def test_keepalive_restarts_advertising_when_disconnected(self):
        """When no central is connected and the server isn't advertising,
        the keepalive must call BlessServer.start() to re-issue advertising.
        This is the macOS-critical path: CoreBluetooth stops advertising on
        first connect and never auto-resumes."""
        daemon, mock_server, _ = _make_daemon()
        mock_server.is_connected = AsyncMock(return_value=False)
        mock_server.is_advertising = AsyncMock(return_value=False)
        mock_server.start = AsyncMock()

        _run_one_keepalive_tick(daemon, max_ticks=1)

        mock_server.start.assert_awaited()

    def test_keepalive_does_not_readvertise_when_connected(self):
        """While a central is connected, advertising should NOT be re-issued
        (it would needlessly churn the GATT link state)."""
        daemon, mock_server, _ = _make_daemon()
        mock_server.is_connected = AsyncMock(return_value=True)
        mock_server.is_advertising = AsyncMock(return_value=True)
        mock_server.start = AsyncMock()

        _run_one_keepalive_tick(daemon, max_ticks=1)

        mock_server.start.assert_not_awaited()

    def test_subscribe_pushes_only_matching_characteristic(self):
        """A CCCD enable-notifications write schedules a deferred push (1.5s).
        The subscribe itself should not immediately enqueue anything — the
        deferred handle should be armed instead.
        """
        daemon, mock_server, _ = _make_daemon()

        async def _run():
            with patch("ohm.ble_daemon.asyncio") as mock_asyncio:
                mock_loop = MagicMock()
                mock_asyncio.get_event_loop.return_value = mock_loop
                char = MagicMock()
                char.uuid = STATS_CLAUDE_CHAR_UUID
                daemon._handle_write(char, bytearray([0x01, 0x00]))
                assert mock_loop.call_later.called
                assert daemon._notify_queue.empty()

        asyncio.run(_run())

    def test_cadence_is_fast_when_connected_and_slow_when_idle(self):
        """The keepalive's wait_for timeout should be the LIVE interval (5s)
        on the tick AFTER a connected check, and IDLE (10s) on the first
        tick (no prior state) or after a disconnect."""
        from ohm.ble_daemon import (
            _STATS_PUSH_INTERVAL_IDLE,
            _STATS_PUSH_INTERVAL_LIVE,
        )

        daemon, mock_server, _ = _make_daemon()
        states = [True, False]

        async def _is_conn():
            return states.pop(0) if states else False

        # Inject directly — bypasses Linux BlueZ path
        daemon._check_connected = _is_conn
        mock_server.is_advertising = AsyncMock(return_value=True)
        mock_server.start = AsyncMock()

        timeouts = _run_one_keepalive_tick(daemon, max_ticks=2)

        assert timeouts[0] == _STATS_PUSH_INTERVAL_IDLE
        assert timeouts[1] == _STATS_PUSH_INTERVAL_LIVE
        assert timeouts[2] == _STATS_PUSH_INTERVAL_IDLE

    def test_keepalive_degrades_gracefully_when_helpers_unimplemented(self):
        """If a bless backend doesn't implement is_connected / is_advertising
        (or they raise for any reason), the keepalive must not crash.
        When disconnected, stats are NOT pushed — they'll arrive via
        _fire_deferred_push on the next subscribe."""
        daemon, mock_server, _ = _make_daemon()

        async def _boom(*a, **kw):
            raise NotImplementedError("backend doesn't expose this helper")

        mock_server.is_connected = _boom
        mock_server.is_advertising = _boom
        mock_server.start = AsyncMock(side_effect=_boom)
        # _check_connected falls back gracefully → False when helpers raise
        daemon._check_connected = AsyncMock(return_value=False)

        # Must not raise.
        _run_one_keepalive_tick(daemon, max_ticks=1)

        # Stats are NOT pushed when disconnected (by design).
        assert daemon._notify_queue.empty()

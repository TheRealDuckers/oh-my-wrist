"""
platform/windows_ble.py — Minimal Windows BLE GATT peripheral server.

Implements the subset of the bless BlessServer API used by ble_daemon.py,
directly against the winrt-* packages (already installed as bleak dependencies).

Why not bless on Windows?
  - bless 0.2.x uses bleak_winrt, which crashes (tp_basicsize mismatch) with
    winrt-runtime 3.x that bleak 3.x installs.
  - bless 0.3.0 requires pysetupdi (not on PyPI) and pins winrt 2.0.0b1
    which conflicts with bleak 3.x (needs winrt >= 3.1).
  No version of bless works cleanly with bleak 3.x on Windows.

This module is used only on win32; Linux/macOS continue to use bless.

Public API (mirrors bless):
    BlessServer               — GATT peripheral server
    BlessGATTCharacteristic   — characteristic type alias (for type hints)
    GATTCharacteristicProperties — property flags (read, notify, …)
    GATTAttributePermissions  — permission flags (readable, …)
"""

from __future__ import annotations

import asyncio
import enum
import logging
from threading import Event
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from winrt.windows.devices.bluetooth.genericattributeprofile import (  # type: ignore[import]
    GattCharacteristicProperties as _WinRTCharProps,
    GattLocalCharacteristic,
    GattLocalCharacteristicParameters,
    GattLocalCharacteristicResult,
    GattLocalService,
    GattProtectionLevel,
    GattReadRequest,
    GattReadRequestedEventArgs,
    GattServiceProvider,
    GattServiceProviderAdvertisingParameters,
    GattServiceProviderResult,
    GattSubscribedClient,
    GattWriteOption,
    GattWriteRequest,
    GattWriteRequestedEventArgs,
)
from winrt.windows.foundation import Deferral  # type: ignore[import]
from winrt.windows.storage.streams import DataReader, DataWriter  # type: ignore[import]

# Optional helper for diagnostic probing of WinRT's short-id recognition.
try:
    from winrt.windows.devices.bluetooth import BluetoothUuidHelper  # type: ignore[import]
except ImportError:  # pragma: no cover — older winrt-python packaging
    BluetoothUuidHelper = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Flag enums — same values as bless (and the Bluetooth spec)
# ---------------------------------------------------------------------------


class GATTCharacteristicProperties(enum.IntFlag):
    broadcast = 0x0001
    read = 0x0002
    write_without_response = 0x0004
    write = 0x0008
    notify = 0x0010
    indicate = 0x0020
    authenticated_signed_writes = 0x0040
    extended_properties = 0x0080
    reliable_write = 0x0100
    writable_auxiliaries = 0x0200


class GATTAttributePermissions(enum.IntFlag):
    readable = 0x1
    writeable = 0x2
    read_encryption_required = 0x4
    write_encryption_required = 0x8


# ---------------------------------------------------------------------------
# Characteristic wrapper — passed to read/write callbacks
# ---------------------------------------------------------------------------


class _Characteristic:
    """Wraps a GattLocalCharacteristic and exposes the bless-compatible API."""

    def __init__(self, uuid: str, obj: GattLocalCharacteristic) -> None:
        self._uuid = uuid
        self.obj = obj
        self._value: bytearray = bytearray()

    @property
    def uuid(self) -> str:
        return self._uuid

    @property
    def value(self) -> bytearray:
        return self._value

    @value.setter
    def value(self, val: bytearray) -> None:
        self._value = val


# Type alias so ble_daemon.py type hints work unchanged
BlessGATTCharacteristic = _Characteristic


# ---------------------------------------------------------------------------
# Internal service state
# ---------------------------------------------------------------------------


class _Service:
    def __init__(self, provider: GattServiceProvider) -> None:
        self.provider = provider
        self.chars: Dict[str, _Characteristic] = {}


def _norm(uuid: Any) -> str:
    """Normalise any UUID-like value to lowercase hyphenated string."""
    return str(UUID(str(uuid)))


# Bluetooth Base UUID: short-form UUIDs are xxxxxxxx-0000-1000-8000-00805F9B34FB.
_BLUETOOTH_BASE_SUFFIX = "-0000-1000-8000-00805f9b34fb"


def _try_short_id(uuid: Any) -> Optional[int]:
    """Return the 16/32-bit short form of a UUID if it matches the Bluetooth
    Base UUID pattern, otherwise None."""
    s = str(uuid).lower()
    if not s.endswith(_BLUETOOTH_BASE_SUFFIX):
        return None
    try:
        return int(s.split("-", 1)[0], 16)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# BLE GATT peripheral server
# ---------------------------------------------------------------------------


class BlessServer:
    """
    Minimal Windows BLE GATT peripheral, API-compatible with bless.BlessServer.

    Only the methods called by ble_daemon.py are implemented.
    """

    def __init__(
        self,
        name: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        **kwargs: Any,
    ) -> None:
        self.name = name
        # Callbacks set by ble_daemon after construction
        self.read_request_func: Optional[Callable[..., bytearray]] = None
        self.write_request_func: Optional[Callable[..., None]] = None

        self._services: Dict[str, _Service] = {}  # service_uuid -> _Service
        self._subscribed_clients: List[GattSubscribedClient] = []
        self._advertising = False
        self._adv_started = Event()

    # ------------------------------------------------------------------
    # Service / characteristic registration
    # ------------------------------------------------------------------

    async def add_new_service(self, uuid: str) -> None:
        norm = _norm(uuid)
        result: GattServiceProviderResult = await GattServiceProvider.create_async(
            UUID(norm)
        )
        sp = result.service_provider
        if sp is None:
            raise RuntimeError(f"Failed to create GATT service provider for {norm}")
        sp.add_advertisement_status_changed(self._on_adv_status_changed)
        self._services[norm] = _Service(sp)
        logger.debug("BLE service created: %s", norm)

    async def add_new_characteristic(
        self,
        service_uuid: str,
        char_uuid: str,
        properties: GATTCharacteristicProperties,
        value: Optional[bytearray],
        permissions: GATTAttributePermissions,
    ) -> None:
        svc_norm = _norm(service_uuid)
        chr_norm = _norm(char_uuid)
        svc = self._services.get(svc_norm)
        if svc is None:
            raise RuntimeError(f"Service {svc_norm} not found")

        local_service: GattLocalService = svc.provider.service
        params = GattLocalCharacteristicParameters()
        params.characteristic_properties = _WinRTCharProps(int(properties))
        # Map permissions → protection level (we only need PLAIN for readable)
        params.read_protection_level = GattProtectionLevel.PLAIN
        params.write_protection_level = GattProtectionLevel.PLAIN

        result: GattLocalCharacteristicResult = (
            await local_service.create_characteristic_async(UUID(chr_norm), params)
        )
        gatt_char = result.characteristic
        if gatt_char is None:
            raise RuntimeError(f"Failed to create characteristic {chr_norm}")

        char = _Characteristic(chr_norm, gatt_char)
        if value is not None:
            char.value = bytearray(value)

        gatt_char.add_read_requested(self._on_read_requested)
        gatt_char.add_write_requested(self._on_write_requested)
        gatt_char.add_subscribed_clients_changed(self._on_subscribed_clients_changed)

        svc.chars[chr_norm] = char
        logger.debug("BLE characteristic created: %s", chr_norm)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, **kwargs: Any) -> None:
        # Discoverable+Connectable so Windows includes the 128-bit service UUID
        # in the ADV_IND primary advertisement packet. Garmin Connect IQ does
        # passive scanning only and reads at most ~20 bytes of ADV_IND, so the
        # service UUID MUST land in the primary packet, not the scan response.
        #
        # We do NOT run a parallel BluetoothLEAdvertisementPublisher: per
        # Microsoft, GattServiceProvider and BluetoothLEAdvertisementPublisher
        # share the same underlying advertising resource and running both
        # concurrently is unsupported (one silently pre-empts the other).
        # The advertised LocalName will be the system Bluetooth device name,
        # which is cosmetic — Garmin connects by service UUID, not name.
        adv_params = GattServiceProviderAdvertisingParameters()
        adv_params.is_discoverable = True
        adv_params.is_connectable = True

        self._adv_started.clear()
        for svc in self._services.values():
            svc.provider.start_advertising_with_parameters(adv_params)
        self._advertising = True
        # Wait up to 5 s for the OS to confirm advertising started
        self._adv_started.wait(timeout=5.0)

        # Diagnostic: log every advertising service provider's status, UUID,
        # and the on-air UUID form (16/32/128-bit). Helps diagnose cases
        # where Windows refuses to compress a Base-form UUID to 16-bit.
        for svc_uuid, svc in self._services.items():
            sp = svc.provider
            sp_uuid = sp.service.uuid
            our_short = _try_short_id(sp_uuid)
            # Ask WinRT itself whether it recognises this UUID as a SIG short ID.
            winrt_short: Optional[int] = None
            if BluetoothUuidHelper is not None:
                try:
                    winrt_short = BluetoothUuidHelper.try_get_short_id(sp_uuid)
                except Exception as exc:
                    logger.debug("BluetoothUuidHelper.try_get_short_id error: %s", exc)
            logger.info(
                "BLE provider: uuid=%s base_form_short=%s winrt_short=%s adv_status=%s",
                sp_uuid,
                ("0x%04X" % our_short) if our_short is not None else "n/a",
                ("0x%04X" % winrt_short) if winrt_short is not None else "n/a",
                sp.advertisement_status,
            )

    async def stop(self) -> None:
        for svc in self._services.values():
            svc.provider.stop_advertising()
        self._advertising = False

    async def is_connected(self) -> bool:
        return len(self._subscribed_clients) > 0

    async def is_advertising(self) -> bool:
        if not self._advertising:
            return False
        return all(
            svc.provider.advertisement_status == 2 for svc in self._services.values()
        )

    # ------------------------------------------------------------------
    # Value access & notification
    # ------------------------------------------------------------------

    def get_characteristic(self, char_uuid: str) -> Optional[_Characteristic]:
        norm = _norm(char_uuid)
        for svc in self._services.values():
            if norm in svc.chars:
                return svc.chars[norm]
        return None

    def update_value(self, service_uuid: str, char_uuid: str) -> bool:
        """Push a BLE notification with the current characteristic value."""
        char = self.get_characteristic(char_uuid)
        if char is None:
            return False
        writer = DataWriter()
        writer.write_bytes(bytes(char.value))
        char.obj.notify_value_async(writer.detach_buffer())
        return True

    # ------------------------------------------------------------------
    # WinRT event handlers
    # ------------------------------------------------------------------

    def _on_adv_status_changed(self, sender: Any, args: Any) -> None:
        # advertisement_status: 0=Created 1=Started (waiting) 2=Started 3=Aborted 4=Stopped
        # Log every transition so we can diagnose stalled advertising.
        try:
            sp_uuid = sender.service.uuid if sender is not None else "?"
            status = args.status if args is not None else None
            logger.info("BLE adv_status_changed uuid=%s status=%s", sp_uuid, status)
        except Exception:
            pass
        if args is not None and args.status == 2:
            self._adv_started.set()

    def _on_read_requested(
        self,
        sender: GattLocalCharacteristic,
        args: GattReadRequestedEventArgs,
    ) -> None:
        if self.read_request_func is None:
            return
        deferral: Optional[Deferral] = args.get_deferral()
        if deferral is None:
            return

        char = self._char_from_obj(sender)
        value = self.read_request_func(char) if char is not None else None
        if value is None:
            value = b"\x00"

        writer = DataWriter()
        writer.write_bytes(bytes(value))

        async def _respond() -> None:
            request: GattReadRequest = await args.get_request_async()
            request.respond_with_value(writer.detach_buffer())
            deferral.complete()

        asyncio.new_event_loop().run_until_complete(_respond())

    def _on_write_requested(
        self,
        sender: GattLocalCharacteristic,
        args: GattWriteRequestedEventArgs,
    ) -> None:
        deferral: Optional[Deferral] = args.get_deferral()
        if deferral is None:
            return

        char = self._char_from_obj(sender)

        async def _process() -> None:
            request: GattWriteRequest = await args.get_request_async()
            reader = DataReader.from_buffer(request.value)
            n = reader.unconsumed_buffer_length
            value = bytearray(reader.read_byte() for _ in range(n))
            if self.write_request_func is not None and char is not None:
                self.write_request_func(char, value)
            if request.option == GattWriteOption.WRITE_WITH_RESPONSE:
                request.respond()
            deferral.complete()

        asyncio.new_event_loop().run_until_complete(_process())

    def _on_subscribed_clients_changed(
        self,
        sender: GattLocalCharacteristic,
        args: Any,
    ) -> None:
        clients = sender.subscribed_clients
        self._subscribed_clients = list(clients) if clients is not None else []
        logger.info(
            "BLE subscribed clients changed: %d client(s)",
            len(self._subscribed_clients),
        )
        # Notify write_request_func so ble_daemon's deferred-push logic triggers.
        # (On Linux/macOS, CCCD writes arrive as explicit write requests; on
        # Windows they fire here instead.  We synthesise the same b"\x01\x00" /
        # b"\x00\x00" values so ble_daemon behaves identically on all platforms.)
        if self.write_request_func is not None:
            char = self._char_from_obj(sender)
            if char is not None:
                cccd_value = b"\x01\x00" if self._subscribed_clients else b"\x00\x00"
                try:
                    self.write_request_func(char, cccd_value)
                except Exception as exc:
                    logger.debug("CCCD write callback error: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _char_from_obj(
        self, sender: GattLocalCharacteristic
    ) -> Optional[_Characteristic]:
        try:
            sender_uuid = _norm(sender.uuid)
        except Exception:
            return None
        for svc in self._services.values():
            if sender_uuid in svc.chars:
                return svc.chars[sender_uuid]
        return None

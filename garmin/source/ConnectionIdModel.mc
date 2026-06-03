// ConnectionIdModel.mc — Persistent BLE connection ID for daemon/watch pairing.
//
// ID 0 preserves the shipped service UUID. Non-zero IDs derive a distinct
// service UUID so the watch ignores nearby oh-my-wrist daemons during scan.

using Toybox.Application;
using Toybox.BluetoothLowEnergy as BLE;
using Toybox.Lang;

module ConnectionIdModel {
    const DEFAULT_ID = 0;
    const MIN_ID = 0;
    const MAX_ID = 255;
    const STORAGE_KEY = "connection_id";
    const HEX = "0123456789ABCDEF";

    var connectionId = DEFAULT_ID;

    function initialize() {
        connectionId = _coerce(Application.Storage.getValue(STORAGE_KEY));
    }

    function getId() {
        return connectionId;
    }

    function setId(value) {
        connectionId = _coerce(value);
        Application.Storage.setValue(STORAGE_KEY, connectionId);
        return connectionId;
    }

    function serviceUuidForCurrentId() {
        return serviceUuidForId(connectionId);
    }

    function serviceUuidForId(value) {
        return BLE.stringToUuid(serviceUuidStringForId(value));
    }

    function serviceUuidStringForId(value) {
        var id = _coerce(value);
        var discriminator = (0x55 + id) % 256;
        return (
            "0FA1" + _hexByte(discriminator) + "B0-0C21-723A-970C-9821F1C5FFAB"
        );
    }

    function _coerce(value) {
        if (value == null) {
            return DEFAULT_ID;
        }
        var n = value as Lang.Number?;
        if (n == null) {
            return DEFAULT_ID;
        }
        if (n < MIN_ID || n > MAX_ID) {
            return DEFAULT_ID;
        }
        return n;
    }

    function _hexByte(value) {
        var high = value / 16;
        var low = value % 16;
        return HEX.substring(high, high + 1) + HEX.substring(low, low + 1);
    }
}

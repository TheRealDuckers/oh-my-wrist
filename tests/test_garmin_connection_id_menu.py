from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GARMIN_SOURCE = ROOT / "garmin" / "source"


def read_garmin_source(filename: str) -> str:
    return (GARMIN_SOURCE / filename).read_text(encoding="utf-8")


def test_menu_item_id_uses_monkey_c_string_equality() -> None:
    source = read_garmin_source("OhMyWristDelegate.mc")

    assert 'item.getId().equals("set_id")' in source
    assert 'item.getId() == "set_id"' not in source


def test_connection_id_editor_handles_physical_keys_directly() -> None:
    source = read_garmin_source("ConnectionIdView.mc")

    assert "function onKey" in source
    assert "WatchUi.KEY_UP" in source
    assert "WatchUi.KEY_DOWN" in source
    assert "WatchUi.KEY_ENTER" in source
    assert "WatchUi.KEY_START" in source
    assert "WatchUi.KEY_ESC" in source
    assert "_view.adjust(-1)" in source
    assert "_view.adjust(1)" in source
    assert "_view.save()" in source


def test_connection_id_save_uses_ble_delegate_when_available() -> None:
    source = read_garmin_source("ConnectionIdView.mc")

    assert "Application.getApp()" in source
    assert "applyConnectionId(_value)" in source
    assert "ConnectionIdModel.setId(_value)" in source

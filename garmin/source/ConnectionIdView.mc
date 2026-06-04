// ConnectionIdView.mc — Small on-watch editor for the BLE connection ID.

using Toybox.Application;
using Toybox.Graphics;
using Toybox.WatchUi;

class ConnectionIdView extends WatchUi.View {
    var _value;
    var _saved;

    function initialize() {
        View.initialize();
        _value = ConnectionIdModel.getId();
        _saved = false;
    }

    function onLayout(dc) {}

    function onUpdate(dc) {
        var w = dc.getWidth();
        var h = dc.getHeight();

        dc.setColor(Palette.bg(), Palette.bg());
        dc.clear();

        dc.setColor(Palette.chrome(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(
            w / 2,
            h * 0.16,
            Graphics.FONT_XTINY,
            WatchUi.loadResource(Rez.Strings.ConnectionIdHeader),
            Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
        );

        dc.setColor(Palette.text(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(
            w / 2,
            h * 0.46,
            Graphics.FONT_SMALL,
            _value.toString(),
            Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
        );

        dc.setColor(Palette.active(), Graphics.COLOR_TRANSPARENT);
        if (_saved) {
            dc.drawText(
                w / 2,
                h * 0.66,
                Graphics.FONT_XTINY,
                WatchUi.loadResource(Rez.Strings.ConnectionIdSaved),
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
            );
            dc.drawText(
                w / 2,
                h * 0.76,
                Graphics.FONT_XTINY,
                WatchUi.loadResource(Rez.Strings.ConnectionIdBackExit),
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
            );
        } else {
            dc.drawText(
                w / 2,
                h * 0.66,
                Graphics.FONT_XTINY,
                WatchUi.loadResource(Rez.Strings.ConnectionIdEditHint),
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
            );
            dc.drawText(
                w / 2,
                h * 0.76,
                Graphics.FONT_XTINY,
                WatchUi.loadResource(Rez.Strings.ConnectionIdSaveHint),
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
            );
        }
    }

    function adjust(delta) {
        _value = _value + delta;
        _saved = false;
        if (_value < ConnectionIdModel.MIN_ID) {
            _value = ConnectionIdModel.MAX_ID;
        } else if (_value > ConnectionIdModel.MAX_ID) {
            _value = ConnectionIdModel.MIN_ID;
        }
        WatchUi.requestUpdate();
    }

    function save() {
        var applied = false;
        var app = Application.getApp();

        if (app != null && app.bleDelegate != null) {
            try {
                applied = app.bleDelegate.applyConnectionId(_value);
            } catch (e) {
                applied = false;
            }
        }

        if (!applied || ConnectionIdModel.getId() != _value) {
            ConnectionIdModel.setId(_value);
        }

        _saved = true;
        WatchUi.requestUpdate();
    }
}

class ConnectionIdDelegate extends WatchUi.BehaviorDelegate {
    var _view;
    var _menuItem;

    function initialize(view, menuItem) {
        BehaviorDelegate.initialize();
        _view = view;
        _menuItem = menuItem;
    }

    function onKey(evt) {
        var key = evt.getKey();

        if (key == WatchUi.KEY_UP) {
            _view.adjust(1);
            return true;
        }

        if (key == WatchUi.KEY_DOWN) {
            _view.adjust(-1);
            return true;
        }

        if (key == WatchUi.KEY_ENTER || key == WatchUi.KEY_START) {
            _saveAndRefreshMenu();
            return true;
        }

        if (key == WatchUi.KEY_ESC) {
            WatchUi.popView(WatchUi.SLIDE_RIGHT);
            return true;
        }

        return false;
    }

    function onNextPage() {
        _view.adjust(-1);
        return true;
    }

    function onPreviousPage() {
        _view.adjust(1);
        return true;
    }

    function onNextMode() {
        _view.adjust(-1);
        return true;
    }

    function onPreviousMode() {
        _view.adjust(1);
        return true;
    }

    function onSelect() {
        _saveAndRefreshMenu();
        return true;
    }

    function onBack() {
        WatchUi.popView(WatchUi.SLIDE_RIGHT);
        return true;
    }

    function _saveAndRefreshMenu() {
        _view.save();
        if (_menuItem != null) {
            _menuItem.setSubLabel(
                WatchUi.loadResource(Rez.Strings.ConnectionIdCurrentPrefix) +
                    " " +
                    ConnectionIdModel.getId().toString()
            );
            WatchUi.requestUpdate();
        }
    }
}

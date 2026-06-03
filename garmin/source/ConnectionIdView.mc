// ConnectionIdView.mc — Small on-watch editor for the BLE connection ID.

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
            "[ connection.id ]",
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
                "Saved. Restart app",
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
            );
            dc.drawText(
                w / 2,
                h * 0.76,
                Graphics.FONT_XTINY,
                "BACK exit",
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
            );
        } else {
            dc.drawText(
                w / 2,
                h * 0.66,
                Graphics.FONT_XTINY,
                "UP/DOWN edit",
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
            );
            dc.drawText(
                w / 2,
                h * 0.76,
                Graphics.FONT_XTINY,
                "SELECT save",
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
        ConnectionIdModel.setId(_value);
        _saved = true;
        WatchUi.requestUpdate();
    }
}

class ConnectionIdDelegate extends WatchUi.BehaviorDelegate {
    var _view;

    function initialize(view) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function onNextPage() {
        _view.adjust(1);
        return true;
    }

    function onPreviousPage() {
        _view.adjust(-1);
        return true;
    }

    function onNextMode() {
        _view.adjust(1);
        return true;
    }

    function onPreviousMode() {
        _view.adjust(-1);
        return true;
    }

    function onSelect() {
        _view.save();
        return true;
    }

    function onBack() {
        WatchUi.popView(WatchUi.SLIDE_RIGHT);
        return true;
    }
}

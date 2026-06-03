// OhMyWristDelegate.mc — View navigation delegate
//
// Handles swipe gestures (touchscreen watches) and UP/DOWN button presses
// (button-only watches) to switch between four widget views:
//
//   View 0: OhMyWristUsageView — Claude usage quota bars (UP from history)
//   View 1: OhMyWristView      — live status + connection dot (initial)
//   View 2: OhMyWristStatsView — Claude session statistics
//   View 3: OhMyWristStatsView — OpenCode session statistics
//
// The delegate is constructed with `viewIndex` so it can no-op at the
// boundaries instead of re-pushing the same view (which Connect IQ would
// otherwise animate as a transition to itself).

using Toybox.WatchUi;

class OhMyWristDelegate extends WatchUi.BehaviorDelegate {
    var _viewIndex;

    function initialize(viewIndex) {
        BehaviorDelegate.initialize();
        _viewIndex = viewIndex;
    }

    // SELECT / START opens the app menu on button watches. MENU does the same
    // on devices with a dedicated menu behavior.
    function onSelect() {
        return _openMenu();
    }

    function onMenu() {
        return _openMenu();
    }

    function _openMenu() {
        var menu = new WatchUi.Menu2({ :title => "Oh-My-Wrist" });
        menu.addItem(
            new WatchUi.MenuItem(
                "Set id",
                "current " + ConnectionIdModel.getId(),
                "set_id",
                {}
            )
        );
        WatchUi.pushView(menu, new OhMyWristMenuDelegate(), WatchUi.SLIDE_UP);
        return true;
    }

    // Swipe left / DOWN button — advance to the next view.
    function onNextPage() {
        if (_viewIndex >= 3) {
            return true; // already on the last view; no transition
        }
        var nextIndex = _viewIndex + 1;
        WatchUi.switchToView(
            _makeView(nextIndex),
            new OhMyWristDelegate(nextIndex),
            WatchUi.SLIDE_LEFT
        );
        return true;
    }

    // Swipe right / UP button — return to the previous view.
    function onPreviousPage() {
        if (_viewIndex <= 0) {
            return true; // already on the first view; no transition
        }
        var prevIndex = _viewIndex - 1;
        WatchUi.switchToView(
            _makeView(prevIndex),
            new OhMyWristDelegate(prevIndex),
            WatchUi.SLIDE_RIGHT
        );
        return true;
    }

    function _makeView(index) {
        if (index == 0) {
            return new OhMyWristUsageView();
        }
        if (index == 2) {
            return new OhMyWristStatsView(
                StatsModel.claude,
                WatchUi.loadResource(Rez.Strings.StatsHeaderClaude)
            );
        }
        if (index == 3) {
            return new OhMyWristStatsView(
                StatsModel.opencode,
                WatchUi.loadResource(Rez.Strings.StatsHeaderOpenCode)
            );
        }
        return new OhMyWristView();
    }
}

class OhMyWristMenuDelegate extends WatchUi.Menu2InputDelegate {
    function initialize() {
        Menu2InputDelegate.initialize();
    }

    function onSelect(item) {
        if (item != null && item.getId().equals("set_id")) {
            var view = new ConnectionIdView();
            WatchUi.pushView(
                view,
                new ConnectionIdDelegate(view),
                WatchUi.SLIDE_LEFT
            );
        }
    }

    function onBack() {
        WatchUi.popView(WatchUi.SLIDE_DOWN);
    }
}

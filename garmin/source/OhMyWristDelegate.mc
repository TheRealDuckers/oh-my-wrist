// OhMyWristDelegate.mc — View navigation delegate
//
// Handles swipe gestures (touchscreen watches) and UP/DOWN button presses
// (button-only watches) to switch between three widget views:
//
//   View 0: OhMyWristView      — live status + connection dot
//   View 1: OhMyWristStatsView — Claude session statistics
//   View 2: OhMyWristStatsView — OpenCode session statistics
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

    // Swipe left / DOWN button — advance to the next view.
    function onNextPage() {
        if (_viewIndex >= 2) {
            return true;  // already on the last view; no transition
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
            return true;  // already on the first view; no transition
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
        if (index == 1) {
            return new OhMyWristStatsView(
                StatsModel.claude,
                WatchUi.loadResource(Rez.Strings.StatsHeaderClaude)
            );
        }
        if (index == 2) {
            return new OhMyWristStatsView(
                StatsModel.opencode,
                WatchUi.loadResource(Rez.Strings.StatsHeaderOpenCode)
            );
        }
        return new OhMyWristView();
    }
}

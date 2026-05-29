// OhMyWristStatsView.mc — Per-provider session statistics screen,
// CLI / terminal aesthetic.
//
//   ┌──────────────────────────┐
//   │   [ claude.session ]     │  ← chrome-gray header, FONT_XTINY
//   ├──────────────────────────┤
//   │   dur     5m 12s         │
//   │   calls   47             │
//   │   files   9              │
//   │   bash    23             │
//   │   idle    45s            │
//   ├──────────────────────────┤
//   │   done: 2m ago           │  ← chrome-gray footer
//   └──────────────────────────┘
//
// Same view class is reused for both Claude and OpenCode stats; the
// constructor receives the StatsData instance and a pre-formatted title
// (the delegate loads "[ claude.session ]" / "[ opencode.session ]" from
// resources).

using Toybox.WatchUi;
using Toybox.Graphics;
using Toybox.System;

class OhMyWristStatsView extends WatchUi.View {

    var _stats;
    var _title;

    function initialize(stats, title) {
        View.initialize();
        _stats = stats;
        _title = title;
    }

    function onLayout(dc) {
        // No XML layout — fully programmatic rendering.
    }

    function onUpdate(dc) {
        var w = dc.getWidth();
        var h = dc.getHeight();

        // Black background.
        dc.setColor(Palette.bg(), Palette.bg());
        dc.clear();

        // Screen shape for chord-width calculations.
        var shape = System.getDeviceSettings().screenShape;
        var chromeFont = Graphics.FONT_XTINY;
        var stepPx = (h * 0.02).toNumber();
        if (stepPx < 1) { stepPx = 1; }

        // Header — chrome gray, centered.
        // Stats can sit slightly lower than the history view because the
        // provider title is longer (notably "opencode") on smaller round
        // screens like Venu 3S.
        var headerTextW = dc.getTextWidthInPixels(_title, chromeFont);
        var headerY = TextUtil.findFitY(
            (h * 0.13).toNumber(),
            (h * 0.24).toNumber(),
            stepPx,
            headerTextW,
            w, h, shape,
            0.90
        );

        dc.setColor(Palette.chrome(), Graphics.COLOR_TRANSPARENT);
        var headerAvail = (TextUtil.getChordWidth(w, h, headerY, shape) * 0.90).toNumber();
        var headerDraw = (headerTextW <= headerAvail)
            ? _title
            : TextUtil.fitMiddleTruncate(dc, _title, chromeFont, headerAvail);
        dc.drawText(
            w / 2,
            headerY,
            chromeFont,
            headerDraw,
            Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
        );

        // Rows — label in chrome, value in primary text.  Both left-justified
        // at fixed column starts to mimic a terminal table.
        var rows = [
            ["dur",   StatsModel.formatDuration(_stats.duration)],
            ["calls", _stats.toolCalls.toString()],
            ["files", _stats.filesEdited.toString()],
            ["bash",  _stats.bashCount.toString()],
            ["idle",  StatsModel.formatDuration(_stats.idleSeconds)]
        ];

        var rowH  = (h * 0.56) / rows.size();
        var baseY = h * 0.26;

        var labelX = (w * 0.22).toNumber();
        var valueX = (w * 0.55).toNumber();

        for (var i = 0; i < rows.size(); i++) {
            var y = baseY + i * rowH;

            // Label — chrome gray.
            dc.setColor(Palette.chrome(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(
                labelX, y,
                Graphics.FONT_TINY,
                rows[i][0],
                Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER
            );

            // Value — primary text, left-aligned so values stack on a
            // common gutter (terminal-table style).
            dc.setColor(Palette.text(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(
                valueX, y,
                Graphics.FONT_TINY,
                rows[i][1],
                Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER
            );
        }

        // Footer — last completion timestamp.
        // Adaptive Y: start at 90%, step inward up to 80% if text clips.
        var footerText = "done: " + _stats.lastCompletion;
        var footerTextW = dc.getTextWidthInPixels(footerText, chromeFont);
        var footerY = TextUtil.findFitY(
            (h * 0.90).toNumber(),
            (h * 0.80).toNumber(),
            stepPx,
            footerTextW,
            w, h, shape,
            0.90
        );

        dc.setColor(Palette.chrome(), Graphics.COLOR_TRANSPARENT);
        var footerAvail = (TextUtil.getChordWidth(w, h, footerY, shape) * 0.90).toNumber();
        var footerDraw = (footerTextW <= footerAvail)
            ? footerText
            : TextUtil.fitMiddleTruncate(dc, footerText, chromeFont, footerAvail);
        dc.drawText(
            w / 2,
            footerY,
            chromeFont,
            footerDraw,
            Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
        );
    }
}

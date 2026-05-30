// OhMyWristUsageView.mc — Claude usage quota screen, CLI / terminal aesthetic.
//
//   ┌──────────────────────────┐
//   │    [ claude.usage ]      │  ← chrome-gray header, FONT_XTINY
//   ├──────────────────────────┤
//   │  S [||||||    ]  58%     │  ← 5-hour session quota
//   │  W [||        ]  18%     │  ← 7-day week quota
//   ├──────────────────────────┤
//   │   sys.status: ok · …     │  ← chrome-gray footer
//   └──────────────────────────┘
//
// Each bar is 10 segment bitmaps (BarFill / BarEmpty); filled = round(pct/10).
// When a window's percentage is unknown (-1), the row shows "n/a".  This
// screen is Claude-only.  Bitmap data comes from UsageModel.

using Toybox.WatchUi;
using Toybox.Graphics;
using Toybox.System;

class OhMyWristUsageView extends WatchUi.View {

    var _title;

    function initialize() {
        View.initialize();
        _title = WatchUi.loadResource(Rez.Strings.UsageHeaderClaude);
    }

    function onLayout(dc) {
    }

    function onUpdate(dc) {
        var w = dc.getWidth();
        var h = dc.getHeight();

        dc.setColor(Palette.bg(), Palette.bg());
        dc.clear();

        var shape = System.getDeviceSettings().screenShape;
        var chromeFont = Graphics.FONT_XTINY;
        var stepPx = (h * 0.02).toNumber();
        if (stepPx < 1) { stepPx = 1; }

        var hasBitmaps = UsageModel.loadBitmaps();

        // Header — chrome gray, centered (adaptive Y like the stats view).
        var headerTextW = dc.getTextWidthInPixels(_title, chromeFont);
        var headerY = TextUtil.findFitY(
            (h * 0.13).toNumber(), (h * 0.24).toNumber(),
            stepPx, headerTextW, w, h, shape, 0.90
        );
        dc.setColor(Palette.chrome(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(
            w / 2, headerY, chromeFont, _title,
            Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
        );

        // Two bar rows centered on h/2.
        var rows = [
            ["S", UsageModel.sessionPct],
            ["W", UsageModel.weekPct]
        ];
        var rowH  = (h * 0.20).toNumber();
        var baseY = (h / 2 - rowH / 2).toNumber();

        for (var i = 0; i < rows.size(); i++) {
            _drawRow(dc, w, baseY + i * rowH, rows[i][0], rows[i][1], hasBitmaps);
        }

        // Footer — reuse the history view's sys.status line.
        var footerText = _buildFooter();
        var footerTextW = dc.getTextWidthInPixels(footerText, chromeFont);
        var footerY = TextUtil.findFitY(
            (h * 0.90).toNumber(), (h * 0.80).toNumber(),
            stepPx, footerTextW, w, h, shape, 0.90
        );
        dc.setColor(Palette.chrome(), Graphics.COLOR_TRANSPARENT);
        var footerAvail = (TextUtil.getChordWidth(w, h, footerY, shape) * 0.90).toNumber();
        var footerDraw = (footerTextW <= footerAvail)
            ? footerText
            : TextUtil.fitMiddleTruncate(dc, footerText, chromeFont, footerAvail);
        dc.drawText(
            w / 2, footerY, chromeFont, footerDraw,
            Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
        );
    }

    // One row: label, 10-cell bar (bitmap or ASCII fallback), trailing percent.
    function _drawRow(dc, w, y, label, pct, hasBitmaps) {
        var labelX = (w * 0.10).toNumber();
        var barX   = (w * 0.22).toNumber();
        var cellW  = UsageModel.barFill != null
            ? (UsageModel.barFill as WatchUi.BitmapResource).getWidth()
            : (w * 0.05).toNumber();
        var cellH  = UsageModel.barFill != null
            ? (UsageModel.barFill as WatchUi.BitmapResource).getHeight()
            : (Graphics.getFontHeight(Graphics.FONT_TINY));
        var filled = UsageModel.filledCells(pct);

        // Label (chrome).
        dc.setColor(Palette.chrome(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(
            labelX, y, Graphics.FONT_TINY, label,
            Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER
        );

        // Bar cells.
        var cellY = (y - cellH / 2).toNumber();
        var valX;
        if (hasBitmaps) {
            for (var c = 0; c < UsageModel.BAR_CELLS; c++) {
                var bmp = (c < filled)
                    ? UsageModel.barFill
                    : UsageModel.barEmpty;
                dc.drawBitmap(barX + c * cellW, cellY, bmp);
            }
            valX = barX + UsageModel.BAR_CELLS * cellW + (w * 0.03).toNumber();
        } else {
            // ASCII fallback: "[||||      ]" in amber.
            var bar = "[";
            for (var c = 0; c < UsageModel.BAR_CELLS; c++) {
                bar += (c < filled) ? "|" : " ";
            }
            bar += "]";
            dc.setColor(Palette.active(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(
                barX, y, Graphics.FONT_TINY, bar,
                Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER
            );
            // Align the trailing value to the measured bar width, since the
            // proportional FONT_TINY string is not BAR_CELLS * cellW wide.
            var barW = dc.getTextWidthInPixels(bar, Graphics.FONT_TINY);
            valX = barX + barW + (w * 0.03).toNumber();
        }

        // Trailing value — "58%" or "n/a".
        var valText = (pct < 0) ? "n/a" : (pct.toString() + "%");
        dc.setColor(Palette.text(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(
            valX, y, Graphics.FONT_TINY, valText,
            Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER
        );
    }

    function _buildFooter() {
        var key = StatusModel.getStatusKey();
        if (key.equals("offline")) {
            return "sys.status: offline";
        }
        var elapsed = StatusModel.getElapsedString();
        if (elapsed == null) {
            return "sys.status: " + key;
        }
        return "sys.status: " + key + " · " + elapsed;
    }
}

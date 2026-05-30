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
// Each bar is 10 vector-drawn cells sized to the row text height; filled =
// round(pct/10).  When a window's percentage is unknown (-1) the bar is empty
// and no trailing value is shown.  This screen is Claude-only.

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
            _drawRow(dc, w, baseY + i * rowH, rows[i][0], rows[i][1]);
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

    // One row: label, 10-cell vector bar sized to the text height, trailing
    // percent (omitted when the window has no data).
    function _drawRow(dc, w, y, label, pct) {
        var labelX = (w * 0.10).toNumber();
        var barX   = (w * 0.22).toNumber();
        var cellW  = (w * 0.05).toNumber();
        // Match the bar to the *visible* glyph box, not the full font cell.
        // getFontHeight = ascent + descent, but our chars (S/W/digits/%) have
        // no descender, so their ink runs from the baseline up by `ascent`.
        // With TEXT_JUSTIFY_VCENTER the font cell is centered on y, putting the
        // baseline at y + (ascent - descent)/2.  Anchor the cell bottom to that
        // baseline and size it to the ascent so top and bottom track the text.
        var ascent  = Graphics.getFontAscent(Graphics.FONT_TINY);
        var descent = Graphics.getFontDescent(Graphics.FONT_TINY);
        var cellH   = ascent;
        var cellY   = (y - (ascent + descent) / 2).toNumber();  // baseline - ascent
        var filled = UsageModel.filledCells(pct);

        // Label (chrome).
        dc.setColor(Palette.chrome(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(
            labelX, y, Graphics.FONT_TINY, label,
            Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER
        );

        // Bar cells — filled = solid amber block, empty = dim outline.
        var gap   = 1;
        var dim   = Palette.dim(Palette.chrome(), 50);
        for (var c = 0; c < UsageModel.BAR_CELLS; c++) {
            var cx = barX + c * cellW;
            if (c < filled) {
                dc.setColor(Palette.active(), Graphics.COLOR_TRANSPARENT);
                dc.fillRectangle(cx, cellY, cellW - gap, cellH);
            } else {
                dc.setColor(dim, Graphics.COLOR_TRANSPARENT);
                dc.drawRectangle(cx, cellY, cellW - gap, cellH);
            }
        }

        // Trailing value — "58%", omitted entirely when the window has no data.
        if (pct >= 0) {
            var valX = barX + UsageModel.BAR_CELLS * cellW + (w * 0.03).toNumber();
            dc.setColor(Palette.text(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(
                valX, y, Graphics.FONT_TINY, pct.toString() + "%",
                Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER
            );
        }
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

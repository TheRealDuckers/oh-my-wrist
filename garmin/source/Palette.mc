// Palette.mc — Single source of truth for the CLI-aesthetic color palette.
//
// Colors are returned as 24-bit RGB integers (0xRRGGBB) so they work on every
// Connect IQ SDK version regardless of whether Graphics.createColor is
// available.  Connect IQ accepts integer literals wherever it accepts a
// Graphics.COLOR_* constant.

module Palette {
    // Background — true black, matches the terminal aesthetic.
    function bg() {
        return 0x000000;
    }

    // Primary text — full white for max contrast on always-on MIP
    // displays. The spec calls for #E0E0E0 but on transflective LCDs it
    // washes out to barely visible.
    function text() {
        return 0xffffff;
    }

    // Accent — warm amber for the in-progress spinner, active row, warnings,
    // and questions (anything that draws the eye).  Still softer than #FFB000
    // but more saturated than the prior pastel so it reads clearly on-device.
    function active() {
        return 0xe89030;
    }

    // Completion — brighter terminal green for the done glyph and stats "done"
    // indicators.  Kept below neon #00FF00, but intentionally more saturated.
    function done() {
        return 0x55dd55;
    }

    // Chrome — CLI gray for header prompt, footer, stats labels.
    // Slightly darker than before to restore contrast against white text.
    function chrome() {
        return 0x888888;
    }

    // Dim a 24-bit RGB color by the given percentage (100 = unchanged,
    // 80 = 20 % dimmer).  Background is black so dimming is a straight
    // per-channel multiplication — no alpha blending required.
    function dim(color, pct) {
        var r = (((color >> 16) & 0xff) * pct) / 100;
        var g = (((color >> 8) & 0xff) * pct) / 100;
        var b = ((color & 0xff) * pct) / 100;
        return (r.toNumber() << 16) | (g.toNumber() << 8) | b.toNumber();
    }
}

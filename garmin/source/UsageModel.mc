// UsageModel.mc — Claude /usage quota state for the usage view.
//
// The desktop daemon pushes a compact JSON payload on USAGE_CHAR_UUID:
//
//   {"s":23,"w":41}
//
//   s  5-hour session quota used percentage (0..100, -1 = unknown/absent)
//   w  7-day week quota used percentage    (0..100, -1 = unknown/absent)
//
// -1 means the data is unavailable (API-key users, or before the first API
// response in a session) — the view draws an empty bar and no trailing value.

using Toybox.Lang;

module UsageModel {
    // 10-cell bars: each filled cell represents 10%.
    const BAR_CELLS = 10;

    var sessionPct = -1; // 5-hour window
    var weekPct = -1; // 7-day window

    // Number of filled cells (0..BAR_CELLS) for a percentage; -1 stays 0.
    function filledCells(pct) {
        if (pct < 0) {
            return 0;
        }
        var n = (pct * BAR_CELLS + 50) / 100; // round to nearest cell
        if (n < 0) {
            return 0;
        }
        if (n > BAR_CELLS) {
            return BAR_CELLS;
        }
        return n;
    }

    // Update state from a compact JSON payload (keys "s", "w"; -1 = absent).
    function parsePayload(jsonStr) {
        try {
            sessionPct = _extractSigned(jsonStr, "\"s\":");
            weekPct = _extractSigned(jsonStr, "\"w\":");
        } catch (e) {
            // Stale display beats a crash.
        }
    }

    // Extract a (possibly negative) integer following the key prefix, or -1.
    function _extractSigned(str, key) {
        var idx = str.find(key);
        if (idx == null) {
            return -1;
        }
        idx += key.length();
        var end = idx;
        while (end < str.length()) {
            var ch = str.substring(end, end + 1);
            if (ch.equals(",") || ch.equals("}")) {
                break;
            }
            end++;
        }
        var token = str.substring(idx, end);
        if (token == null || token.length() == 0) {
            return -1;
        }
        var n = token.toNumber();
        return n == null ? -1 : n;
    }
}

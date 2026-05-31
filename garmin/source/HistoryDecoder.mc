// HistoryDecoder.mc — Parse the per-event binary frame received on
// HISTORY_CHAR_UUID into a {:icon, :flags, :text} dictionary.
//
// Frame layout (matches src/ohm/protocol.py):
//
//   +--------+--------+--------+--------+----------------+
//   | ver:1  | icon:1 | flags:1| len:1  | text: len B    |
//   +--------+--------+--------+--------+----------------+

using Toybox.Lang;
using Toybox.StringUtil;
using Toybox.System;

module HistoryDecoder {
    const PROTOCOL_VERSION = 0x01;

    // Flag bits — mirror src/ohm/icons.py.
    const FLAG_SPINNER = 0x01;
    const FLAG_ACCENT = 0x02;
    const FLAG_DIM = 0x04;
    const FLAG_CLEAR_PREV_SPINNER = 0x08;

    // Decode a frame ByteArray.  Returns null on any malformed input so the
    // watch never crashes on a future protocol version or a truncated read.
    function decodeFrame(bytes) {
        if (bytes == null) {
            return null;
        }
        if (!(bytes instanceof Lang.ByteArray)) {
            System.println("HistoryDecoder: non-ByteArray input: " + bytes);
            return null;
        }
        if (bytes.size() < 4) {
            return null;
        }
        if (bytes[0] != PROTOCOL_VERSION) {
            return null;
        }

        var icon = bytes[1];
        var flags = bytes[2];
        var len = bytes[3];
        if (4 + len > bytes.size()) {
            return null;
        }

        var text = "";
        if (len > 0) {
            try {
                text = StringUtil.convertEncodedString(
                    bytes.slice(4, 4 + len),
                    {
                        :fromRepresentation
                        =>
                        StringUtil.REPRESENTATION_BYTE_ARRAY,
                        :toRepresentation
                        =>
                        StringUtil.REPRESENTATION_STRING_PLAIN_TEXT,
                        :encoding => StringUtil.CHAR_ENCODING_UTF8,
                    }
                );
            } catch (e) {
                System.println(
                    "HistoryDecoder: UTF-8 decode failed (len=" + len + ")"
                );
                return null;
            }
        }

        return { :icon => icon, :flags => flags, :text => text };
    }
}

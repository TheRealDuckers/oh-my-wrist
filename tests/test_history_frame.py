"""
Tests for the HISTORY frame wire format — bit-level invariants the watch
parser depends on.  Mirrors the byte layout described in protocol.py:

    +--------+--------+--------+--------+----------------+
    | ver:1  | icon:1 | flags:1| len:1  | text: len B    |
    +--------+--------+--------+--------+----------------+
"""

from __future__ import annotations


from ohm.history_encoder import decode_frame, encode_event
from ohm.icons import (
    FLAG_ACCENT,
    FLAG_CLEAR_PREV_SPINNER,
    FLAG_DIM,
    FLAG_SPINNER,
    IconId,
)
from ohm.protocol import (
    ENTRY_TEXT_MAX,
    MAX_FRAME_LEN,
    PROTOCOL_VERSION,
)
from ohm.provider_types import CanonicalEvent


def _ev(canonical: str, **kwargs) -> CanonicalEvent:
    base = {"provider": "claude", "canonical_event": canonical}
    base.update(kwargs)
    return CanonicalEvent(**base)


# ============================================================================
# Header bytes
# ============================================================================


class TestHeader:
    def test_first_byte_is_protocol_version(self):
        assert encode_event(_ev("tool_end"))[0] == PROTOCOL_VERSION

    def test_second_byte_is_icon_id(self):
        frame = encode_event(_ev("tool_start", tool_name="Bash", label="ls"))
        assert frame[1] == int(IconId.PLAY)

    def test_third_byte_carries_flags(self):
        frame = encode_event(_ev("session_error"))
        # session_error has ACCENT | CLEAR_PREV_SPINNER
        assert frame[2] & FLAG_ACCENT
        assert frame[2] & FLAG_CLEAR_PREV_SPINNER

    def test_fourth_byte_is_text_length(self):
        ev = _ev("status", status_text="abc")
        frame = encode_event(ev)
        assert frame[3] == 3
        assert frame[4 : 4 + 3] == b"abc"


# ============================================================================
# Size guarantees
# ============================================================================


class TestSizeGuarantees:
    def test_max_frame_len(self):
        assert MAX_FRAME_LEN == 4 + ENTRY_TEXT_MAX
        assert MAX_FRAME_LEN <= 24  # comfortably under ATT MTU 23 effective payload

    def test_no_event_exceeds_max_frame_len(self):
        for ce in (
            "tool_start",
            "tool_end",
            "session_start",
            "session_idle",
            "session_stop",
            "session_error",
            "file_edit",
            "todo_update",
            "permission_request",
            "permission_reply",
            "command",
            "status",
            "unknown",
        ):
            frame = encode_event(
                _ev(
                    ce,
                    tool_name="Bash",
                    label="x" * 200,
                    path="/y" * 50,
                    status_text="z" * 200,
                    provider_event="long.event.name",
                )
            )
            assert len(frame) <= MAX_FRAME_LEN

    def test_text_section_respects_entry_text_max(self):
        frame = encode_event(_ev("status", status_text="z" * 100))
        assert frame[3] <= ENTRY_TEXT_MAX


# ============================================================================
# Flag bit values are distinct
# ============================================================================


class TestFlagBits:
    def test_flag_bits_distinct(self):
        flags = [FLAG_SPINNER, FLAG_ACCENT, FLAG_DIM, FLAG_CLEAR_PREV_SPINNER]
        assert len({f for f in flags}) == len(flags)

    def test_flag_bits_within_byte(self):
        for f in (FLAG_SPINNER, FLAG_ACCENT, FLAG_DIM, FLAG_CLEAR_PREV_SPINNER):
            assert 0 < f <= 0xFF

    def test_flag_bits_are_single_bit(self):
        for f in (FLAG_SPINNER, FLAG_ACCENT, FLAG_DIM, FLAG_CLEAR_PREV_SPINNER):
            assert bin(f).count("1") == 1


# ============================================================================
# Decoder round-trip via Python mirror
# ============================================================================


class TestDecoderRoundTrip:
    def test_every_flag_combination_roundtrips(self):
        """Build a synthetic frame for every combination of the four defined
        flag bits and verify decode preserves the bits exactly."""
        for flags in range(0x10):  # bits 0..3
            frame = bytes([PROTOCOL_VERSION, int(IconId.PLAY), flags, 2]) + b"hi"
            decoded = decode_frame(frame)
            assert decoded is not None
            assert decoded["flags"] == flags

    def test_decode_handles_zero_length_text(self):
        frame = bytes([PROTOCOL_VERSION, int(IconId.CHECK), 0, 0])
        decoded = decode_frame(frame)
        assert decoded == {"icon": int(IconId.CHECK), "flags": 0, "text": ""}

    def test_decode_preserves_unicode(self):
        # Encode then decode through the real pipeline
        ev = _ev("status", status_text="αβγ")
        decoded = decode_frame(encode_event(ev))
        assert decoded["text"] == "αβγ"

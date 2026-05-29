"""
Tests for status_formatter.py — what little remains.

The legacy ``format_status`` / ``format_canonical`` API has been removed; its
behaviour is now covered by the binary frame encoder (see
``tests/test_history_encoder.py`` and ``tests/test_end_to_end_normalization.py``).

This file retains only the UTF-8 truncation tests.  ``is_destructive_command``
is exercised by ``tests/test_destructive.py``.
"""

from __future__ import annotations

from ohm.status_formatter import _utf8_truncate


class TestUtf8Truncate:
    def test_ascii_short(self):
        assert _utf8_truncate("hello", 20) == "hello"

    def test_ascii_exact(self):
        assert _utf8_truncate("A" * 20, 20) == "A" * 20
        assert len(_utf8_truncate("A" * 20, 20).encode("utf-8")) == 20

    def test_ascii_truncated(self):
        result = _utf8_truncate("A" * 30, 20)
        assert len(result.encode("utf-8")) == 20

    def test_4byte_char_not_split(self):
        # U+10000 (𐀀) = 4 bytes; 6 × 4 = 24 bytes — must truncate to 5 chars (20 bytes)
        result = _utf8_truncate("\U00010000" * 6, 20)
        assert len(result.encode("utf-8")) <= 20
        result.encode("utf-8").decode("utf-8")

    def test_mixed_ascii_multibyte(self):
        s = "run: npm install"
        assert _utf8_truncate(s, 20) == s

    def test_three_byte_char_not_split(self):
        # "€" = 3 bytes; 8 × 3 = 24 → truncated cleanly
        result = _utf8_truncate("€" * 8, 20)
        assert len(result.encode("utf-8")) <= 20
        result.encode("utf-8").decode("utf-8")

    def test_result_always_valid_utf8(self):
        cases = [
            "run: npm install",
            "edit: main.py",
            "read: server.py",
            "web: fetching...",
            "todo: update",
            "tool: SomeFutureTool",
            "ok: done",
            "start: session",
            "ファイル" * 20,
            "\U00010000" * 30,
        ]
        for s in cases:
            for limit in (0, 1, 4, 10, 18, 20, 22):
                out = _utf8_truncate(s, limit)
                assert len(out.encode("utf-8")) <= limit
                out.encode("utf-8").decode("utf-8")

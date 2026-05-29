"""
test_status_formatter_extended.py — Extended UTF-8 truncation edge cases.

The display-string formatter (``format_canonical`` / ``format_status``) has
been removed in favour of the binary frame protocol; per-event display
assertions live in ``tests/test_history_encoder.py``.

This file keeps the deep UTF-8 truncation suite plus the label-extraction
helpers (basename, first-word) that moved into ``history_encoder``.
"""

from __future__ import annotations

from ohm.history_encoder import _basename, _first_word, _utf8_truncate


# ============================================================================
# _utf8_truncate edge cases
# ============================================================================


class TestUtf8TruncateEdgeCases:
    def test_empty_string_any_limit(self):
        for limit in (0, 1, 20, 100):
            assert _utf8_truncate("", limit) == ""

    def test_zero_limit_returns_empty(self):
        assert _utf8_truncate("hello", 0) == ""

    def test_limit_of_one_ascii(self):
        assert _utf8_truncate("hello", 1) == "h"

    def test_limit_of_one_with_multibyte_char(self):
        # "€" (3 bytes) at limit=1 → empty (can't fit a 3-byte char)
        assert _utf8_truncate("€", 1) == ""

    def test_four_byte_char_cut_at_1(self):
        assert _utf8_truncate("\U00010000", 1) == ""

    def test_four_byte_char_cut_at_4(self):
        assert _utf8_truncate("\U00010000\U00010000", 4) == "\U00010000"

    def test_four_byte_char_cut_at_5(self):
        # 5 bytes can hold one 4-byte char but not part of the next
        assert _utf8_truncate("\U00010000\U00010000", 5) == "\U00010000"

    def test_three_byte_char_cut_at_2(self):
        assert _utf8_truncate("€€", 2) == ""

    def test_three_byte_char_cut_at_3(self):
        assert _utf8_truncate("€€", 3) == "€"

    def test_two_byte_char_cut_at_1(self):
        assert _utf8_truncate("ñ", 1) == ""

    def test_two_byte_char_cut_at_2(self):
        assert _utf8_truncate("ñ", 2) == "ñ"

    def test_mixed_1_2_3_4_byte_chars(self):
        s = "a" + "ñ" + "€" + "\U00010000"  # 1+2+3+4 = 10 bytes
        assert _utf8_truncate(s, 10) == s
        truncated = _utf8_truncate(s, 6)
        assert len(truncated.encode("utf-8")) <= 6
        truncated.encode("utf-8").decode("utf-8")

    def test_exact_boundary_not_truncated(self):
        s = "\U00010000" * 5  # 20 bytes
        assert _utf8_truncate(s, 20) == s

    def test_large_limit_returns_full_string(self):
        s = "hello"
        assert _utf8_truncate(s, 1000) == s

    def test_result_never_longer_than_input(self):
        for s in ["abc", "ñ", "€€€", "\U00010000\U00010000", "mixed ñ€\U00010000"]:
            for limit in (0, 1, 2, 4, 8, 20, 100):
                assert len(_utf8_truncate(s, limit)) <= len(s)

    def test_idempotent_double_truncation(self):
        s = "\U00010000" * 5
        once = _utf8_truncate(s, 10)
        twice = _utf8_truncate(once, 10)
        assert once == twice

    def test_nul_byte_string(self):
        s = "a\x00b"
        assert _utf8_truncate(s, 20) == s

    def test_newline_and_tab(self):
        s = "a\nb\tc"
        assert _utf8_truncate(s, 20) == s


# ============================================================================
# _basename
# ============================================================================


class TestBasenameEdgeCases:
    def test_empty_string(self):
        assert _basename("") == ""

    def test_filename_only(self):
        assert _basename("file.py") == "file.py"

    def test_unix_absolute_path(self):
        assert _basename("/usr/local/bin/python") == "python"

    def test_unix_relative_path(self):
        assert _basename("a/b/c.py") == "c.py"

    def test_trailing_slash_returns_empty(self):
        assert _basename("/usr/local/") == ""

    def test_dotfile(self):
        assert _basename("/home/user/.bashrc") == ".bashrc"

    def test_no_extension(self):
        assert _basename("/usr/bin/python3") == "python3"

    def test_unicode_filename(self):
        assert _basename("/path/ファイル.py") == "ファイル.py"

    def test_deeply_nested_path(self):
        assert _basename("/a/b/c/d/e/f/g/h.py") == "h.py"

    def test_multiple_dots(self):
        assert _basename("/path/file.tar.gz") == "file.tar.gz"


# ============================================================================
# _first_word
# ============================================================================


class TestFirstWordEdgeCases:
    def test_empty_string(self):
        assert _first_word("") == ""

    def test_single_word(self):
        assert _first_word("ls") == "ls"

    def test_multiple_words(self):
        assert _first_word("ls -la /tmp") == "ls"

    def test_leading_whitespace(self):
        assert _first_word("   ls -la") == "ls"

    def test_tab_separated(self):
        assert _first_word("ls\t-la") == "ls"

    def test_path_command(self):
        assert _first_word("/usr/bin/python script.py") == "/usr/bin/python"

    def test_env_var_prefix(self):
        assert _first_word("FOO=bar ls") == "FOO=bar"

    def test_pipe_in_command(self):
        assert _first_word("ls | grep py") == "ls"

    def test_semicolon_in_command(self):
        assert _first_word("ls; pwd") == "ls;"

    def test_whitespace_only(self):
        assert _first_word("   \t  ") == ""

    def test_newline_in_command(self):
        assert _first_word("ls\necho") == "ls"

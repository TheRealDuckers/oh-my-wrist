"""
Tests for statusline_relay.py

Covers:
- Extraction of session/week percentages from rate_limits (present/absent/null).
- Chaining: a saved previous statusLine command's stdout is passed through.
- Robustness: exits 0 on malformed/empty stdin even with no daemon running.
"""

from __future__ import annotations

import json
import subprocess
import sys

import ohm.statusline_relay as relay

_MODULE = "ohm.statusline_relay"


def _run(stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", _MODULE],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestParseUsage:
    def test_both_present(self):
        raw = json.dumps(
            {
                "rate_limits": {
                    "five_hour": {"used_percentage": 23.5},
                    "seven_day": {"used_percentage": 41.2},
                }
            }
        )
        assert relay._parse_usage(raw) == (24, 41)

    def test_rate_limits_absent(self):
        assert relay._parse_usage(json.dumps({"model": {"id": "x"}})) == (-1, -1)

    def test_window_independently_absent(self):
        raw = json.dumps({"rate_limits": {"five_hour": {"used_percentage": 10}}})
        assert relay._parse_usage(raw) == (10, -1)

    def test_null_percentage(self):
        raw = json.dumps(
            {"rate_limits": {"five_hour": {"used_percentage": None}, "seven_day": {}}}
        )
        assert relay._parse_usage(raw) == (-1, -1)

    def test_empty_and_malformed(self):
        assert relay._parse_usage("") == (-1, -1)
        assert relay._parse_usage("{not json}") == (-1, -1)

    def test_clamped_to_range(self):
        raw = json.dumps(
            {
                "rate_limits": {
                    "five_hour": {"used_percentage": 150},
                    "seven_day": {"used_percentage": -5},
                }
            }
        )
        assert relay._parse_usage(raw) == (100, 0)


class TestChaining:
    def test_passes_through_previous_stdout(self, tmp_path, monkeypatch):
        prev = tmp_path / "prev_statusline"
        prev.write_text("printf 'CHAINED'", encoding="utf-8")
        monkeypatch.setattr(relay, "_PREV_STATUSLINE_PATH", prev)

        captured = {}

        class _FakeStdout:
            def write(self, s):
                captured["out"] = captured.get("out", "") + s

        monkeypatch.setattr(sys, "stdout", _FakeStdout())
        relay._chain_previous("{}")
        assert captured.get("out") == "CHAINED"

    def test_no_prev_file_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(relay, "_PREV_STATUSLINE_PATH", tmp_path / "missing")
        relay._chain_previous("{}")  # must not raise


class TestExitCode:
    def test_exits_zero_on_valid_input(self):
        payload = json.dumps({"rate_limits": {"five_hour": {"used_percentage": 5}}})
        assert _run(payload).returncode == 0

    def test_exits_zero_on_empty_stdin(self):
        assert _run("").returncode == 0

    def test_exits_zero_on_malformed_json(self):
        assert _run("{not valid json}").returncode == 0

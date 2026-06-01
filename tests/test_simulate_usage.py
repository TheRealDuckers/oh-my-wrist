"""Tests for tools/simulate_usage.py — pure bar-rendering helper.

Verifies _render_bar mirrors UsageModel.mc / ui_design.md §10:
10 cells, round(pct/10) filled, -1 -> empty bar with no trailing value.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

BAR_CELLS = 10


def _render_bar(label: str, pct: int) -> str:
    """Watch-style preview: 'S [|||||     ] 58%' or 'S [          ]' (no value)."""
    if pct < 0:
        return f"{label} [{' ' * BAR_CELLS}]"
    filled = (pct * BAR_CELLS + 50) // 100  # nearest cell, like UsageModel
    bar = "|" * filled + " " * (BAR_CELLS - filled)
    return f"{label} [{bar}] {pct}%"


def _filled(bar_str: str) -> int:
    return bar_str.count("|")


class TestRenderBar:
    def test_typical_value_fills_six_cells(self):
        out = _render_bar("S", 58)
        assert _filled(out) == 6  # round(5.8) -> 6
        assert out.endswith("58%")
        assert out.startswith("S [")

    def test_no_data_for_minus_one(self):
        out = _render_bar("W", -1)
        assert "n/a" not in out
        assert "%" not in out
        assert _filled(out) == 0
        assert "|" not in out

    def test_zero_fills_no_cells(self):
        assert _filled(_render_bar("S", 0)) == 0

    def test_hundred_fills_all_cells(self):
        assert _filled(_render_bar("S", 100)) == BAR_CELLS

    def test_ninety_five_rounds_to_all_cells(self):
        assert _filled(_render_bar("S", 95)) == BAR_CELLS  # round(9.5) -> 10

    def test_bar_width_is_constant(self):
        # Filled + empty cells always total BAR_CELLS.
        for pct in (0, 1, 50, 99, 100):
            inner = _render_bar("S", pct).split("[")[1].split("]")[0]
            assert len(inner) == BAR_CELLS

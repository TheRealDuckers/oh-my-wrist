"""
icons.py — Append-only icon registry for the watch history protocol.

Each canonical event is mapped (in :mod:`history_encoder`) to one of these
icon IDs.  The watch holds a parallel catalogue (``garmin/source/IconCatalog.mc``)
that maps each ID back to a glyph or procedural drawing.

Registry discipline
-------------------
* Icon IDs are an **append-only** namespace.  Never renumber, never remove,
  never repurpose.  Adding a new icon takes the next free ID.
* Daemon and watch ship together, so version skew is bounded — but the
  append-only rule means an older watch build receiving a newer icon ID
  simply renders a ``?`` glyph (forward-compat fallback) instead of
  corrupting the display.

Flag bits travel alongside the icon byte in every frame and modify how the
watch renders or reacts to the entry.
"""

from __future__ import annotations

from enum import IntEnum


class IconId(IntEnum):
    """Append-only catalogue of watch-display icons."""

    NONE = 0x00
    PLAY = 0x01  # shell / command
    PENCIL = 0x02  # file edit / write
    EYE = 0x03  # read
    GLOBE = 0x04  # web fetch / search
    CLIPBOARD = 0x05  # todo update
    WRENCH = 0x06  # agent / unknown tool
    CHECK = 0x07  # tool done / permission approved
    GREEN_CIRCLE = 0x08  # session start
    PAUSE = 0x09  # session idle / waiting
    STOP = 0x0A  # session stopped
    WARNING = 0x0B  # session error
    QUESTION = 0x0C  # permission request / unknown
    NO_ENTRY = 0x0D  # permission denied
    STATUS_DOT = 0x0E  # generic status


# Flag bits in the per-frame ``flags`` byte.
FLAG_SPINNER = 0x01  # entry is in-progress; watch animates a spinner
FLAG_ACCENT = 0x02  # render icon in accent colour (warnings, errors)
FLAG_DIM = 0x04  # render entry dimmed (reserved, unused in v1)
FLAG_CLEAR_PREV_SPINNER = (
    0x08  # on receive, clear SPINNER on the most recent prior entry
)

# Sentinel used internally for `no flags`.
FLAGS_NONE = 0x00

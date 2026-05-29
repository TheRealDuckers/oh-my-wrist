"""
config.py — User preferences for the oh-my-wrist daemon.

Preferences are stored in ~/.oh-my-wrist/config.json.  All fields have
sensible defaults so the file does not need to exist before first use.

Schema
------
{
  "haptic_enabled": true,
  "quiet_start": "22:00",
  "quiet_end": "08:00"
}

Quiet-hours logic
-----------------
If ``quiet_start`` and ``quiet_end`` define a window that spans midnight
(e.g. 22:00 → 08:00) the check wraps correctly.  If they are equal the
quiet window is treated as disabled (never quiet).
"""

from __future__ import annotations

import json
import tempfile
import os
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".oh-my-wrist"
CONFIG_PATH = CONFIG_DIR / "config.json"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULTS: dict = {
    "haptic_enabled": True,
    "quiet_start": "22:00",
    "quiet_end": "08:00",
}


# ---------------------------------------------------------------------------
# Config dataclass-like object
# ---------------------------------------------------------------------------


class Config:
    """Loaded configuration with typed accessors."""

    def __init__(self, data: dict) -> None:
        self.haptic_enabled: bool = bool(
            data.get("haptic_enabled", _DEFAULTS["haptic_enabled"])
        )
        self.quiet_start: str = str(data.get("quiet_start", _DEFAULTS["quiet_start"]))
        self.quiet_end: str = str(data.get("quiet_end", _DEFAULTS["quiet_end"]))

    # ------------------------------------------------------------------
    # Quiet-hours helpers
    # ------------------------------------------------------------------

    def _parse_time(self, hhmm: str) -> dtime:
        """Parse an 'HH:MM' string into a :class:`datetime.time` object."""
        try:
            h, m = hhmm.split(":")
            return dtime(int(h), int(m))
        except (ValueError, AttributeError):
            return dtime(0, 0)

    def is_quiet(self, now: Optional[dtime] = None) -> bool:
        """Return True if the current local time falls within the quiet window.

        If ``quiet_start == quiet_end`` the window is treated as disabled and
        this method always returns False.
        """
        qs = self._parse_time(self.quiet_start)
        qe = self._parse_time(self.quiet_end)

        if qs == qe:
            # Window disabled
            return False

        t = now if now is not None else datetime.now().time()

        if qs < qe:
            # Normal window (e.g. 08:00 → 22:00)
            return qs <= t < qe
        else:
            # Overnight window (e.g. 22:00 → 08:00)
            return t >= qs or t < qe

    def haptic_allowed(self, now: Optional[dtime] = None) -> bool:
        """Return True if haptic feedback may be sent right now."""
        return self.haptic_enabled and not self.is_quiet(now)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "haptic_enabled": self.haptic_enabled,
            "quiet_start": self.quiet_start,
            "quiet_end": self.quiet_end,
        }

    def __repr__(self) -> str:
        return (
            f"Config(haptic_enabled={self.haptic_enabled!r}, "
            f"quiet_start={self.quiet_start!r}, "
            f"quiet_end={self.quiet_end!r})"
        )


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def load_config() -> Config:
    """Load config from disk; return defaults if the file is absent or corrupt."""
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}
    except FileNotFoundError:
        data = {}
    except (json.JSONDecodeError, OSError):
        data = {}
    return Config({**_DEFAULTS, **data})


def save_config(cfg: Config) -> None:
    """Atomically write *cfg* to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = json.dumps(cfg.to_dict(), indent=2) + "\n"
    # Atomic write via temp file + rename
    fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, prefix=".config_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, CONFIG_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def set_haptic(enabled: bool) -> Config:
    """Toggle haptic alerts and persist the change."""
    cfg = load_config()
    cfg.haptic_enabled = enabled
    save_config(cfg)
    return cfg


def set_quiet_start(hhmm: str) -> Config:
    """Set quiet-hours start time (HH:MM) and persist."""
    cfg = load_config()
    cfg.quiet_start = hhmm
    save_config(cfg)
    return cfg


def set_quiet_end(hhmm: str) -> Config:
    """Set quiet-hours end time (HH:MM) and persist."""
    cfg = load_config()
    cfg.quiet_end = hhmm
    save_config(cfg)
    return cfg

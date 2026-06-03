"""
test_config.py — Tests for ohm.config

Coverage
--------
- Config defaults when file is absent
- load_config with valid JSON
- load_config with corrupt JSON falls back to defaults
- load_config with non-dict JSON falls back to defaults
- save_config writes valid JSON with trailing newline
- save_config is atomic (no temp files left behind)
- set_haptic(True/False) round-trips correctly
- set_quiet_start / set_quiet_end persist
- is_quiet: normal window (no midnight crossing)
- is_quiet: overnight window (crosses midnight)
- is_quiet: window disabled (start == end)
- is_quiet: boundary values (exactly at start, exactly at end)
- haptic_allowed: True when haptic on and not quiet
- haptic_allowed: False when haptic off
- haptic_allowed: False when haptic on but quiet
- Config.__repr__ contains key fields
- Partial JSON (only some keys) merges with defaults
"""

from __future__ import annotations

import json
import os
import stat
from datetime import time as dtime
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_dir(tmp_path: Path):
    """Patch CONFIG_DIR and CONFIG_PATH to a temp directory."""
    config_dir = tmp_path / ".oh-my-wrist"
    config_path = config_dir / "config.json"
    return config_dir, config_path


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    def test_defaults_when_file_absent(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import load_config

            cfg = load_config()
        assert cfg.haptic_enabled is True
        assert cfg.quiet_start == "22:00"
        assert cfg.quiet_end == "08:00"
        assert cfg.connection_id == 0

    def test_defaults_with_empty_dict(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        config_dir.mkdir(parents=True)
        config_path.write_text("{}\n", encoding="utf-8")
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import load_config

            cfg = load_config()
        assert cfg.haptic_enabled is True
        assert cfg.quiet_start == "22:00"

    def test_corrupt_json_falls_back(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        config_dir.mkdir(parents=True)
        config_path.write_text("NOT JSON {{{", encoding="utf-8")
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import load_config

            cfg = load_config()
        assert cfg.haptic_enabled is True  # default

    def test_non_dict_json_falls_back(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        config_dir.mkdir(parents=True)
        config_path.write_text("[1, 2, 3]\n", encoding="utf-8")
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import load_config

            cfg = load_config()
        assert cfg.haptic_enabled is True

    def test_partial_json_merges_with_defaults(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        config_dir.mkdir(parents=True)
        config_path.write_text('{"haptic_enabled": false}\n', encoding="utf-8")
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import load_config

            cfg = load_config()
        assert cfg.haptic_enabled is False
        assert cfg.quiet_start == "22:00"  # still default
        assert cfg.quiet_end == "08:00"
        assert cfg.connection_id == 0

    def test_connection_id_loaded_from_json(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        config_dir.mkdir(parents=True)
        config_path.write_text('{"connection_id": 42}\n', encoding="utf-8")
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import load_config

            cfg = load_config()
        assert cfg.connection_id == 42

    def test_invalid_connection_id_falls_back_to_default(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        config_dir.mkdir(parents=True)
        config_path.write_text('{"connection_id": 999}\n', encoding="utf-8")
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import load_config

            cfg = load_config()
        assert cfg.connection_id == 0


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------


class TestSaveConfig:
    def test_save_writes_valid_json(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import Config, save_config

            cfg = Config(
                {"haptic_enabled": False, "quiet_start": "23:00", "quiet_end": "07:00"}
            )
            save_config(cfg)
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["haptic_enabled"] is False
        assert data["quiet_start"] == "23:00"
        assert data["quiet_end"] == "07:00"
        assert data["connection_id"] == 0

    def test_save_trailing_newline(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import Config, save_config

            save_config(Config({}))
        raw = config_path.read_bytes()
        assert raw.endswith(b"\n")

    def test_save_no_temp_files_left(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import Config, save_config

            save_config(Config({}))
        files = list(config_dir.iterdir())
        assert len(files) == 1
        assert files[0].name == "config.json"

    def test_save_creates_config_dir(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        assert not config_dir.exists()
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import Config, save_config

            save_config(Config({}))
        assert config_dir.exists()

    def test_save_config_uses_private_permissions(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import Config, save_config

            save_config(Config({}))

        if os.name == "posix":
            assert stat.S_IMODE(config_dir.stat().st_mode) == 0o700
            assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


class TestControlToken:
    def test_control_token_is_persisted_with_private_permissions(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import get_control_token

            token1 = get_control_token()
            token2 = get_control_token()

        token_path = config_dir / "control.token"
        assert token1 == token2
        assert len(token1) >= 32
        assert token_path.read_text(encoding="utf-8").strip() == token1
        if os.name == "posix":
            assert stat.S_IMODE(config_dir.stat().st_mode) == 0o700
            assert stat.S_IMODE(token_path.stat().st_mode) == 0o600

    def test_control_token_recovers_empty_file(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        config_dir.mkdir(parents=True)
        (config_dir / "control.token").write_text("", encoding="utf-8")

        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import get_control_token

            token = get_control_token()

        assert len(token) >= 32
        assert (config_dir / "control.token").read_text(encoding="utf-8").strip()
        assert not (config_dir / ".control.token.lock").exists()


# ---------------------------------------------------------------------------
# set_haptic / set_quiet_start / set_quiet_end
# ---------------------------------------------------------------------------


class TestSetters:
    def test_set_haptic_false(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import set_haptic, load_config

            set_haptic(False)
            cfg = load_config()
        assert cfg.haptic_enabled is False

    def test_set_haptic_true(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import set_haptic, load_config

            set_haptic(False)
            set_haptic(True)
            cfg = load_config()
        assert cfg.haptic_enabled is True

    def test_set_quiet_start(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import set_quiet_start, load_config

            set_quiet_start("23:30")
            cfg = load_config()
        assert cfg.quiet_start == "23:30"

    def test_set_quiet_end(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import set_quiet_end, load_config

            set_quiet_end("06:30")
            cfg = load_config()
        assert cfg.quiet_end == "06:30"

    def test_set_returns_config_object(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import set_haptic

            result = set_haptic(False)
        from ohm.config import Config

        assert isinstance(result, Config)

    def test_set_connection_id(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import set_connection_id, load_config

            set_connection_id(255)
            cfg = load_config()
        assert cfg.connection_id == 255

    def test_set_connection_id_rejects_out_of_range(self, tmp_path):
        config_dir, config_path = _make_config_dir(tmp_path)
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
        ):
            from ohm.config import set_connection_id

            try:
                set_connection_id(256)
            except ValueError as exc:
                assert "connection_id" in str(exc)
            else:
                raise AssertionError("set_connection_id accepted 256")


# ---------------------------------------------------------------------------
# is_quiet
# ---------------------------------------------------------------------------


class TestIsQuiet:
    def _cfg(self, qs, qe, haptic=True):
        from ohm.config import Config

        return Config({"haptic_enabled": haptic, "quiet_start": qs, "quiet_end": qe})

    # Normal window (no midnight crossing): 08:00 → 22:00
    def test_normal_window_inside(self):
        cfg = self._cfg("08:00", "22:00")
        assert cfg.is_quiet(dtime(12, 0)) is True

    def test_normal_window_outside_before(self):
        cfg = self._cfg("08:00", "22:00")
        assert cfg.is_quiet(dtime(7, 59)) is False

    def test_normal_window_outside_after(self):
        cfg = self._cfg("08:00", "22:00")
        assert cfg.is_quiet(dtime(22, 0)) is False

    def test_normal_window_at_start(self):
        cfg = self._cfg("08:00", "22:00")
        assert cfg.is_quiet(dtime(8, 0)) is True

    def test_normal_window_just_before_end(self):
        cfg = self._cfg("08:00", "22:00")
        assert cfg.is_quiet(dtime(21, 59)) is True

    # Overnight window (crosses midnight): 22:00 → 08:00
    def test_overnight_window_at_start(self):
        cfg = self._cfg("22:00", "08:00")
        assert cfg.is_quiet(dtime(22, 0)) is True

    def test_overnight_window_midnight(self):
        cfg = self._cfg("22:00", "08:00")
        assert cfg.is_quiet(dtime(0, 0)) is True

    def test_overnight_window_early_morning(self):
        cfg = self._cfg("22:00", "08:00")
        assert cfg.is_quiet(dtime(3, 30)) is True

    def test_overnight_window_just_before_end(self):
        cfg = self._cfg("22:00", "08:00")
        assert cfg.is_quiet(dtime(7, 59)) is True

    def test_overnight_window_at_end(self):
        cfg = self._cfg("22:00", "08:00")
        assert cfg.is_quiet(dtime(8, 0)) is False

    def test_overnight_window_midday(self):
        cfg = self._cfg("22:00", "08:00")
        assert cfg.is_quiet(dtime(14, 0)) is False

    # Disabled window (start == end)
    def test_disabled_window_never_quiet(self):
        cfg = self._cfg("00:00", "00:00")
        assert cfg.is_quiet(dtime(0, 0)) is False
        assert cfg.is_quiet(dtime(12, 0)) is False
        assert cfg.is_quiet(dtime(23, 59)) is False

    # Invalid time strings fall back to 00:00
    def test_invalid_time_string_does_not_crash(self):
        cfg = self._cfg("bad", "also_bad")
        # Both parse to 00:00 → disabled window → never quiet
        assert cfg.is_quiet(dtime(12, 0)) is False


# ---------------------------------------------------------------------------
# haptic_allowed
# ---------------------------------------------------------------------------


class TestHapticAllowed:
    def _cfg(self, haptic, qs="22:00", qe="08:00"):
        from ohm.config import Config

        return Config({"haptic_enabled": haptic, "quiet_start": qs, "quiet_end": qe})

    def test_allowed_when_haptic_on_and_not_quiet(self):
        cfg = self._cfg(True)
        # 14:00 is outside 22:00→08:00 overnight window
        assert cfg.haptic_allowed(dtime(14, 0)) is True

    def test_not_allowed_when_haptic_off(self):
        cfg = self._cfg(False)
        assert cfg.haptic_allowed(dtime(14, 0)) is False

    def test_not_allowed_when_quiet(self):
        cfg = self._cfg(True)
        # 23:00 is inside 22:00→08:00 overnight window
        assert cfg.haptic_allowed(dtime(23, 0)) is False

    def test_not_allowed_when_haptic_off_and_quiet(self):
        cfg = self._cfg(False)
        assert cfg.haptic_allowed(dtime(23, 0)) is False


# ---------------------------------------------------------------------------
# Config.__repr__
# ---------------------------------------------------------------------------


class TestConfigRepr:
    def test_repr_contains_haptic(self):
        from ohm.config import Config

        cfg = Config({"haptic_enabled": False})
        assert "haptic_enabled=False" in repr(cfg)

    def test_repr_contains_quiet_start(self):
        from ohm.config import Config

        cfg = Config({"quiet_start": "21:00"})
        assert "21:00" in repr(cfg)

    def test_repr_contains_connection_id(self):
        from ohm.config import Config

        cfg = Config({"connection_id": 7})
        assert "connection_id=7" in repr(cfg)

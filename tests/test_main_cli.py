"""Tests for the Click CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner


def _make_config_dir(tmp_path: Path):
    config_dir = tmp_path / ".oh-my-wrist"
    config_path = config_dir / "config.json"
    return config_dir, config_path


class TestSetIdCommand:
    def test_set_id_persists_and_notifies_running_daemon(self, tmp_path):
        from ohm.main import cli

        config_dir, config_path = _make_config_dir(tmp_path)
        send = AsyncMock()
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
            patch("ohm.main._read_pid", return_value=1234),
            patch("ohm.main._is_running", return_value=True),
            patch("ohm.main.send_to_daemon", send),
        ):
            result = CliRunner().invoke(cli, ["set-id", "42"])

        assert result.exit_code == 0
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["connection_id"] == 42
        sent_msg = send.await_args.args[0]
        assert sent_msg.canonical_event == "config_update"
        assert sent_msg.meta["connection_id"] == 42
        assert (
            sent_msg.meta["control_token"]
            == (config_dir / "control.token").read_text(encoding="utf-8").strip()
        )
        assert "update queued" in result.output

    def test_set_id_skips_ipc_when_daemon_stopped(self, tmp_path):
        from ohm.main import cli

        config_dir, config_path = _make_config_dir(tmp_path)
        send = AsyncMock()
        with (
            patch("ohm.config.CONFIG_DIR", config_dir),
            patch("ohm.config.CONFIG_PATH", config_path),
            patch("ohm.main._read_pid", return_value=None),
            patch("ohm.main.send_to_daemon", send),
        ):
            result = CliRunner().invoke(cli, ["set-id", "7"])

        assert result.exit_code == 0
        assert "next daemon start" in result.output
        send.assert_not_awaited()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["connection_id"] == 7

    def test_set_id_rejects_out_of_range(self):
        from ohm.main import cli

        result = CliRunner().invoke(cli, ["set-id", "256"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

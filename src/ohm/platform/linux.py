"""
platform/linux.py — Linux-specific service management via systemd user units.

The daemon is registered as a systemd --user service so it starts on login
and can be controlled with `systemctl --user`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SERVICE_NAME = "oh-my-wrist"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
SERVICE_PATH = SYSTEMD_USER_DIR / f"{SERVICE_NAME}.service"

_SERVICE_TEMPLATE = """\
[Unit]
Description=oh-my-wrist BLE Daemon
After=network.target bluetooth.target

[Service]
Type=simple
ExecStart={executable} start --foreground
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""


def install_service() -> None:
    """Install and enable the systemd user service."""
    executable = shutil.which("oh-my-wrist") or sys.executable
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)

    SERVICE_PATH.write_text(_SERVICE_TEMPLATE.format(executable=executable))

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", SERVICE_NAME],
        check=True,
    )


def uninstall_service() -> None:
    """Disable and remove the systemd user service."""
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", SERVICE_NAME],
        capture_output=True,
    )
    SERVICE_PATH.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


def service_status() -> str:
    """Return a human-readable status string for the systemd service."""
    result = subprocess.run(
        ["systemctl", "--user", "status", SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or result.stderr.strip()

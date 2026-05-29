"""
platform/windows.py — Windows-specific service management via Task Scheduler.

The daemon is registered as a Task Scheduler task that starts on user login.
Requires Windows 10 Build 17763+ for WinRT BLE support.
"""

from __future__ import annotations

import getpass
import shutil
import subprocess
import sys
from pathlib import Path

TASK_NAME = "OhMyWristDaemon"

_TASK_XML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2"
      xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{username}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{username}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{executable}</Command>
      <Arguments>start --foreground</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def install_service() -> None:
    """Register the Task Scheduler task."""
    executable = shutil.which("oh-my-wrist") or sys.executable
    username = getpass.getuser()
    xml_content = _TASK_XML_TEMPLATE.format(
        username=username,
        executable=executable,
    )

    xml_path = Path.home() / ".oh-my-wrist" / "task.xml"
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    # Write as UTF-16 LE (required by schtasks /XML)
    xml_path.write_bytes(xml_content.encode("utf-16"))

    result = subprocess.run(
        [
            "schtasks",
            "/Create",
            "/F",
            "/TN",
            TASK_NAME,
            "/XML",
            str(xml_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"schtasks /Create failed: {result.stderr.strip()}")


def uninstall_service() -> None:
    """Delete the Task Scheduler task."""
    subprocess.run(
        ["schtasks", "/Delete", "/F", "/TN", TASK_NAME],
        capture_output=True,
    )


def service_status() -> str:
    """Return a human-readable status string for the scheduled task."""
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "Task not found"

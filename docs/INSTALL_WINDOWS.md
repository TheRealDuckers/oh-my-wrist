# Windows Installation Guide

Platform-specific setup for Oh-My-Wrist on Windows. For general installation steps, see the main [README](../README.md).

## Prerequisites

- Python 3.12+
- Windows 10 Build 17763 (October 2018 Update) or later
- `pip` (included with Python installer)

## BLE Permissions

Windows requires Bluetooth access for apps. Verify it is enabled:

1. Open **Settings** → **Privacy** → **Bluetooth**
2. Ensure "Allow apps to access your Bluetooth" is **On**

No additional group membership or capabilities are needed — the daemon uses the WinRT Bluetooth GATT APIs directly.

## System Service

The installer registers a **Task Scheduler** entry that runs the daemon at user logon with automatic restart.

```powershell
# Install hooks + service
oh-my-wrist install

# Manual service control
oh-my-wrist start
oh-my-wrist stop
oh-my-wrist status
```

To inspect or modify the scheduled task:

```powershell
# View task in Task Scheduler
schtasks /query /tn "OhMyWrist"

# Delete task manually (if needed)
schtasks /delete /tn "OhMyWrist" /f
```

The daemon log is at `%USERPROFILE%\.oh-my-wrist\daemon.log`.

## IPC Transport

On Windows the daemon listens on a named pipe at `\\.\pipe\ohm` (instead of a Unix socket).

## Troubleshooting

### WinRT Bluetooth errors

- Ensure Bluetooth is turned on in Windows Settings → Bluetooth & devices.
- Update your Bluetooth adapter driver via Device Manager.
- The WinRT BLE peripheral API requires Windows 10 Build 17763+. Check your build:
  ```powershell
  winver
  ```

### Daemon not starting

```powershell
# Run in foreground to see errors
oh-my-wrist start --foreground

# Check the log
oh-my-wrist logs -n 50
```

Common cause: another application is holding the BLE peripheral role. Close other BLE apps and retry.

### Task Scheduler entry not created

```powershell
# Re-register
oh-my-wrist uninstall
oh-my-wrist install

# Verify
schtasks /query /tn "OhMyWrist"
```

### Watch can't discover the daemon

- Ensure the watch and PC are within BLE range (~10 m line of sight).
- Verify `oh-my-wrist status` shows the daemon is advertising.
- Try toggling Bluetooth off/on in Windows Settings.

### Python not found after install

If `oh-my-wrist` is not recognized after `pip install`:

```powershell
# Ensure Python Scripts directory is in PATH
python -m ohm.main start --foreground
```

Or add `%APPDATA%\Python\Python312\Scripts` to your system PATH.

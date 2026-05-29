# macOS Installation Guide

Platform-specific setup for Oh-My-Wrist on macOS. For general installation steps, see the main [README](../README.md).

## Prerequisites

- Python 3.12+
- macOS 12 (Monterey) or later
- `pip` (or `pipx` for isolated installs)

## BLE Permissions

macOS requires explicit Bluetooth access for terminal applications. The first time the daemon starts, macOS will prompt you to grant access.

If you dismissed the prompt or need to grant it manually:

1. Open **System Settings** → **Privacy & Security** → **Bluetooth**
2. Click **+** and add your terminal app (Terminal.app, iTerm2, Alacritty, etc.)
3. Restart the daemon: `oh-my-wrist stop && oh-my-wrist start`

The daemon uses Core Bluetooth via the [`bless`](https://github.com/kevincar/bless) library — no additional drivers needed.

## System Service

The installer registers a **launchd LaunchAgent** (`~/Library/LaunchAgents/com.oh-my-wrist.daemon.plist`) that starts the daemon at login.

```bash
# Install hooks + service
oh-my-wrist install

# Manual service control
launchctl kickstart gui/$(id -u)/com.oh-my-wrist.daemon
launchctl kill SIGTERM gui/$(id -u)/com.oh-my-wrist.daemon

# Check if loaded
launchctl print gui/$(id -u)/com.oh-my-wrist.daemon
```

The daemon log is at `~/.oh-my-wrist/daemon.log`.

## IPC Transport

On macOS the daemon listens on a Unix domain socket at `/tmp/ohm.sock`.

## Troubleshooting

### Bluetooth permission popup not appearing

- Ensure you're running the daemon from the terminal app that needs permission (not via SSH or a remote session).
- Try removing and re-adding the terminal app in Privacy & Security → Bluetooth.

### Daemon not advertising

```bash
# Check daemon status
oh-my-wrist status

# Run in foreground to see errors
oh-my-wrist start --foreground
```

Common cause: another process is already using the BLE peripheral role. Close any other BLE peripheral apps and retry.

### Service not starting at login

```bash
# Verify the plist is loaded
launchctl list | grep oh-my-wrist

# Re-register
oh-my-wrist uninstall
oh-my-wrist install
```

### Watch pairs but immediately disconnects

- Ensure the watch is not connected to another BLE peripheral that conflicts.
- Forget the device on the watch (Settings → Sensors & Accessories → remove Oh-My-Wrist) and let it re-pair.

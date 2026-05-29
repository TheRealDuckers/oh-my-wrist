# Linux Installation Guide

Platform-specific setup for Oh-My-Wrist on Linux. For general installation steps, see the main [README](../README.md).

## Prerequisites

- Python 3.12+
- BlueZ 5.x (installed by default on most distributions)
- `pip` (or `pipx` for isolated installs)

## BLE Permissions

The daemon uses BlueZ to advertise a GATT service. Your user must be in the `bluetooth` group:

```bash
sudo usermod -aG bluetooth $USER
```

**Log out and back in** (or reboot) for the group change to take effect.

Verify membership:

```bash
groups | grep bluetooth
```

The daemon registers a BlueZ **NoInputNoOutput** pairing agent automatically — the watch pairs without a PIN prompt.

## System Service

The installer registers a **systemd user unit** (`~/.config/systemd/user/oh-my-wrist.service`) that starts the daemon at login and restarts on crash.

```bash
# Install hooks + service
oh-my-wrist install

# Manual service control
systemctl --user start oh-my-wrist
systemctl --user stop oh-my-wrist
systemctl --user restart oh-my-wrist
systemctl --user status oh-my-wrist

# View service logs
journalctl --user -u oh-my-wrist -f
```

The daemon also writes its own log to `~/.oh-my-wrist/daemon.log`.

## IPC Transport

On Linux the daemon listens on a Unix domain socket at `/tmp/ohm.sock`.

## Troubleshooting

### Bluetooth adapter not found

```bash
# Check adapter is visible
bluetoothctl list

# Ensure the bluetooth service is running
sudo systemctl status bluetooth
sudo systemctl start bluetooth
```

### Permission denied on BLE operations

- Confirm your user is in the `bluetooth` group (see above).
- Some distributions require `CAP_NET_ADMIN`. If you see `PermissionError` in the daemon log, try:
  ```bash
  sudo setcap cap_net_admin+ep $(which python3.12)
  ```

### Service not starting

```bash
# Check for errors
systemctl --user status oh-my-wrist
journalctl --user -u oh-my-wrist --no-pager -n 30

# Re-register the service
oh-my-wrist uninstall
oh-my-wrist install
```

### Daemon running but watch can't connect

```bash
# Verify the daemon is advertising
oh-my-wrist status

# Check BLE advertising
bluetoothctl show | grep Powered
# Should show: Powered: yes
```

If the adapter is powered off:

```bash
bluetoothctl power on
```

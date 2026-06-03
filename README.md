<p align="center">
  <img src="static/ohw_logo_transparent.png" alt="Oh-My-Wrist Logo" width="240"/>
</p>

<h1 align="center">Oh-My-Wrist</h1>

![Oh-My-Wrist](https://img.shields.io/badge/Oh--My--Wrist-blue)
![GitHub stars](https://img.shields.io/github/stars/yazon/oh-my-wrist?style=social)
![GitHub top language](https://img.shields.io/github/languages/top/yazon/oh-my-wrist)
![GitHub repo size](https://img.shields.io/github/repo-size/yazon/oh-my-wrist)
![GitHub last commit](https://img.shields.io/github/last-commit/yazon/oh-my-wrist?color=red)
![GitHub License](https://img.shields.io/github/license/yazon/oh-my-wrist)

**Oh-My-Wrist** displays real-time [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) and [OpenCode](https://opencode.ai) activity on your Garmin smartwatch over Bluetooth Low Energy. See what your AI coding assistant is doing — right on your wrist.

## Key Features

- ⌚ **Real-time BLE updates** — tool calls, file edits, and session state streamed to your watch
- 🤖 **Multi-provider** — supports Claude Code and OpenCode simultaneously, tracked independently
- 🖥️ **Cross-platform** — runs on Linux, macOS, and Windows
- 📳 **Haptic alerts** — vibration patterns for idle, session done, destructive commands, and agent completion
- 🖤 **CLI-styled watch UI** — terminal aesthetic with animated amber spinner, event stack, and per-provider stats
- 🌙 **Quiet hours** — suppress vibrations during configurable time windows

<p align="center">
  <img src="static/demo.gif" alt="Oh-My-Wrist Watch Demo" width="400"/>
</p>

## Quick Start

### 1. Install the Python daemon

```bash
pip install oh-my-wrist
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install oh-my-wrist
```

### 2. Configure providers and system service

```bash
oh-my-wrist install
```

This automatically:
- Patches **Claude Code** hooks in `~/.claude/settings.json`
- Configures a **Claude Code statusLine** that streams `/usage` quota to the watch (chaining any existing statusLine)
- Installs the **OpenCode** TypeScript plugin (when `opencode` is on PATH)
- Registers a background **system service** (systemd / launchd / Task Scheduler)

To install a single provider only:

```bash
oh-my-wrist install --provider claude
oh-my-wrist install --provider opencode
```

### 3. Install the Garmin watch app

1. Open the `garmin/` directory in VS Code with the Monkey C extension.
2. Build the project (Connect IQ SDK 9.1+).
3. Side-load the `.prg` file to your watch via USB (copy to `GARMIN/APPS/`), or publish to the Connect IQ Store.

### 4. Start coding

```bash
oh-my-wrist start
```

Open the **Oh-My-Wrist** app on your watch — it connects automatically and updates in real time.

## Platform Guides

| Platform | Guide |
|----------|-------|
| 🐧 Linux | [docs/INSTALL_LINUX.md](docs/INSTALL_LINUX.md) |
| 🍎 macOS | [docs/INSTALL_MACOS.md](docs/INSTALL_MACOS.md) |
| 🪟 Windows | [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md) |

## Usage

Start the daemon in the background (or foreground for debugging):

```bash
oh-my-wrist start
oh-my-wrist start --foreground
```

Start a Claude Code or OpenCode session — the watch updates automatically.

### Watch Navigation

Four swipeable views (left/right or UP/DOWN on button watches). History is the
initial view — swipe/press **UP** for the Claude usage screen, **DOWN** for the
per-provider stats screens:

| View | Direction from History | Content |
|------|------------------------|---------|
| Claude Usage | UP | `/usage`-style quota bars: session (5h) and week (7d), htop-style |
| History | — (initial) | CLI-style event stack (3 visible rows with animated spinner) |
| Claude Stats | DOWN | Session duration, tool calls, files edited, bash count, idle time |
| OpenCode Stats | DOWN ×2 | Same metrics, isolated from Claude |

The usage screen is Claude-only and shows an empty bar with no percentage
when quota data is unavailable (API-key users, or before the first API
response in a session).

### CLI Commands

| Command | Purpose |
|---------|---------|
| `oh-my-wrist start [-f\|--foreground]` | Start the BLE daemon |
| `oh-my-wrist stop` | Stop the daemon |
| `oh-my-wrist status` | Show daemon PID, service status, hook/plugin state |
| `oh-my-wrist install [--provider claude\|opencode\|both]` | Configure hooks, plugin, and OS service |
| `oh-my-wrist uninstall [--provider …]` | Remove hooks, plugin, and service |
| `oh-my-wrist test [message] [--provider claude\|opencode]` | Send a test message to the daemon |
| `oh-my-wrist config [--show\|--haptic on\|off\|--quiet-start HH:MM\|--quiet-end HH:MM]` | View or update configuration |
| `oh-my-wrist opencode install\|uninstall\|status` | Manage the OpenCode plugin |
| `oh-my-wrist logs [-n LINES]` | Tail the daemon log |

## Configuration

Settings are stored at `~/.oh-my-wrist/config.json` and take effect immediately (no restart needed).

```bash
# View current config
oh-my-wrist config --show

# Toggle haptic alerts
oh-my-wrist config --haptic on
oh-my-wrist config --haptic off

# Set quiet hours (vibrations suppressed)
oh-my-wrist config --quiet-start 22:00 --quiet-end 08:00
```

| Setting | Default | Description |
|---------|---------|-------------|
| `haptic_enabled` | `true` | Enable/disable all vibration alerts |
| `quiet_start` | `22:00` | Start of quiet window (HH:MM) |
| `quiet_end` | `08:00` | End of quiet window (HH:MM) |

## Supported Devices

Requires a Garmin watch with BLE and Connect IQ 3.1+ support:

- Fenix 7 / 7S / 7X
- Fenix 8 43mm / 47mm
- Forerunner 265 / 955
- Venu 3 / 3S
- Vivoactive 3 / 3 Music / 4

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Watch can't find daemon | Run `oh-my-wrist status` — verify daemon is advertising. Restart with `oh-my-wrist stop && oh-my-wrist start`. |
| Hook not firing | Run `oh-my-wrist status` — confirm hooks in `~/.claude/settings.json`. Re-run `oh-my-wrist install`. |
| OpenCode not updating | Check plugin: `oh-my-wrist opencode status`. Re-install: `oh-my-wrist opencode install`. |
| BLE permission errors | See your platform guide: [Linux](docs/INSTALL_LINUX.md) · [macOS](docs/INSTALL_MACOS.md) · [Windows](docs/INSTALL_WINDOWS.md) |
| Daemon crashes on start | Run `oh-my-wrist start --foreground` to see the error. Check `oh-my-wrist logs`. |

## Uninstall

```bash
oh-my-wrist uninstall
pip uninstall oh-my-wrist
```

To remove the watch app, delete it via Garmin Express or the Connect IQ app on your phone.

## Development

```bash
# pip
pip install -e ".[dev]"
pytest tests/

# or uv
uv venv && uv pip install -e ".[dev]"
uv run pytest

oh-my-wrist start --foreground
```

## License

This project is licensed under the BSD 3-Clause License. See the [LICENSE](LICENSE) file for details.

---

**⌚ Ready to see your AI assistant's activity on your wrist? Install Oh-My-Wrist and start coding!**

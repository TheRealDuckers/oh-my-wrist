"""
install.py — Auto-installer for oh-my-wrist.

Step A: Patch Claude Code's global ~/.claude/settings.json with the
        required hook configuration (atomic write to prevent corruption).
Step B: Install the OpenCode plugin into the project's .opencode/plugins/
        directory (if an OpenCode project is detected).
Step C: Register the BLE daemon as a system service appropriate for the
        current platform (launchd / systemd / Task Scheduler).

Provider detection
------------------
- Claude Code is always installed (global ~/.claude/settings.json).
- OpenCode is installed when the current working directory (or any ancestor
  up to the filesystem root) contains a `.opencode/` directory.
- For compatibility with older repository layouts, we also treat a project as
  OpenCode-enabled when it contains `opencode/opencode.json` or
  `opencode/plugins/` and bootstrap `.opencode/` during installation.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from loguru import logger

# ---------------------------------------------------------------------------
# Claude Code hook configuration
# ---------------------------------------------------------------------------

_HOOK_COMMAND = "oh-my-wrist hook"

_HOOK_ENTRY = {"type": "command", "command": _HOOK_COMMAND, "async": True}

_HOOK_EVENTS = {
    "PreToolUse": [{"matcher": "", "hooks": [_HOOK_ENTRY]}],
    "PostToolUse": [{"matcher": "", "hooks": [_HOOK_ENTRY]}],
    "Notification": [{"hooks": [_HOOK_ENTRY]}],
    "Stop": [{"hooks": [_HOOK_ENTRY]}],
}

CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# ---------------------------------------------------------------------------
# OpenCode plugin configuration
# ---------------------------------------------------------------------------

# Name of the plugin file placed inside ~/.config/opencode/plugins/
OPENCODE_PLUGIN_FILENAME = "oh_my_wrist_opencode.ts"

# Bundled plugin source shipped with this package
_PLUGIN_SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "opencode"
    / "plugins"
    / OPENCODE_PLUGIN_FILENAME
)

# Global plugin directory — auto-loaded by OpenCode at startup
_OPENCODE_GLOBAL_PLUGINS_DIR = Path.home() / ".config" / "opencode" / "plugins"

# Legacy per-project entry (kept for removal/migration)
_OPENCODE_PLUGIN_ENTRY = f"./plugins/{OPENCODE_PLUGIN_FILENAME}"


# ---------------------------------------------------------------------------
# Atomic JSON write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write *data* as JSON to *path* using an atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* using an atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Claude Code hook patching
# ---------------------------------------------------------------------------


def _is_hook_present(hooks_list: list[dict]) -> bool:
    """Return True if our hook command is already present in *hooks_list*."""
    for entry in hooks_list:
        for hook in entry.get("hooks", []):
            if hook.get("command") == _HOOK_COMMAND:
                return True
    return False


def patch_claude_settings() -> None:
    """Merge the oh-my-wrist hook entries into Claude Code's settings.json."""
    if CLAUDE_SETTINGS_PATH.exists():
        try:
            settings = json.loads(CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning(
                "Existing settings.json is not valid JSON — creating a fresh one"
            )
            settings = {}
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    changed = False

    for event, entries in _HOOK_EVENTS.items():
        existing = hooks.setdefault(event, [])
        if not _is_hook_present(existing):
            existing.extend(entries)
            changed = True
            logger.info("Added hook for event '{}'", event)
        else:
            logger.info("Hook for event '{}' already present — skipping", event)

    if changed:
        _atomic_write_json(CLAUDE_SETTINGS_PATH, settings)
        logger.info("Claude Code settings patched at {}", CLAUDE_SETTINGS_PATH)
    else:
        logger.info("No changes needed to Claude Code settings")


def remove_claude_hooks() -> None:
    """Remove oh-my-wrist hook entries from Claude Code's settings.json."""
    if not CLAUDE_SETTINGS_PATH.exists():
        return

    try:
        settings = json.loads(CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    hooks = settings.get("hooks", {})
    changed = False

    for event in list(hooks.keys()):
        original = hooks[event]
        filtered = [entry for entry in original if not _is_hook_present([entry])]
        if len(filtered) != len(original):
            hooks[event] = filtered
            changed = True
            logger.info("Removed hook for event '{}'", event)

    if changed:
        _atomic_write_json(CLAUDE_SETTINGS_PATH, settings)
        logger.info("Claude Code hooks removed from {}", CLAUDE_SETTINGS_PATH)


# ---------------------------------------------------------------------------
# OpenCode project detection
# ---------------------------------------------------------------------------


def _has_legacy_opencode_layout(root: Path) -> bool:
    """Return True if *root* uses the legacy `opencode/` scaffold.

    Older project templates stored OpenCode files under `opencode/` in the
    repository rather than `.opencode/` in the project root.
    """
    legacy_config = root / "opencode" / "opencode.json"
    legacy_plugins_dir = root / "opencode" / "plugins"
    return legacy_config.is_file() or legacy_plugins_dir.is_dir()


def find_opencode_project_root(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default: cwd) to find an OpenCode project root.

    A root is considered OpenCode-enabled if it contains either:
      - `.opencode/` (current layout), or
      - `opencode/opencode.json` / `opencode/plugins/` (legacy layout).

    Returns the project root Path if found, otherwise None.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        if (current / ".opencode").is_dir() or _has_legacy_opencode_layout(current):
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def is_opencode_project(start: Path | None = None) -> bool:
    """Return True if the current directory is inside an OpenCode project."""
    return find_opencode_project_root(start) is not None


def is_opencode_installed() -> bool:
    """Return True if OpenCode appears to be installed on this system."""
    # Check for the global config directory or the opencode binary
    if _OPENCODE_GLOBAL_PLUGINS_DIR.parent.exists():
        return True
    # Check PATH for the opencode binary
    import shutil

    return shutil.which("opencode") is not None


# ---------------------------------------------------------------------------
# OpenCode plugin installation
# ---------------------------------------------------------------------------


def _get_plugin_source() -> str:
    """Return the TypeScript plugin source text.

    Tries the bundled file first; falls back to an embedded minimal stub
    so that installation never fails even if the package is partially
    installed.
    """
    if _PLUGIN_SOURCE_PATH.exists():
        return _PLUGIN_SOURCE_PATH.read_text(encoding="utf-8")

    # Fallback: inline minimal plugin stub
    return _OPENCODE_PLUGIN_STUB


_OPENCODE_PLUGIN_STUB = """\
// oh_my_wrist_opencode.ts — auto-generated stub
// Full source is in opencode/plugins/ of the oh-my-wrist package.
import * as net from "net";

const SOCKET_PATH = process.platform === "win32"
  ? String.raw`\\\\\\\\.\\\\pipe\\\\ohm`
  : "/tmp/ohm.sock";

async function sendToDaemon(payload: object): Promise<void> {
  const json = JSON.stringify(payload) + "\\n";
  return new Promise<void>((resolve) => {
    try {
      const sock = net.createConnection(SOCKET_PATH);
      sock.on("connect", () => { sock.write(json, "utf8", () => { sock.end(); resolve(); }); });
      sock.on("error", () => resolve());
      sock.setTimeout(500, () => { sock.destroy(); resolve(); });
    } catch { resolve(); }
  });
}

export const OhMyWristPlugin = async (_ctx: unknown) => {
  return {
    "tool.execute.before": async (input: any, output: any) => {
      await sendToDaemon({
        provider: "opencode", provider_event: "tool.execute.before",
        canonical_event: "tool_start", session_id: input?.sessionID ?? null,
        tool_name: input?.tool ?? null, label: null, path: null,
        status_text: null, active: true, alert_type: 0,
        ts: Date.now() / 1000, meta: {},
      });
    },
    "tool.execute.after": async (input: any, output: any) => {
      await sendToDaemon({
        provider: "opencode", provider_event: "tool.execute.after",
        canonical_event: "tool_end", session_id: input?.sessionID ?? null,
        tool_name: input?.tool ?? null, label: null, path: null,
        status_text: null, active: false, alert_type: 0,
        ts: Date.now() / 1000, meta: {},
      });
    },
    event: async ({ event }: { event: any }) => {
      if (!event?.type) return;
      const type = event.type;
      if (type === "session.created" || type === "session.idle" || type === "session.error") {
        const ce = type === "session.created" ? "session_start"
          : type === "session.idle" ? "session_idle" : "session_error";
        await sendToDaemon({
          provider: "opencode", provider_event: type,
          canonical_event: ce, session_id: event.sessionId ?? null,
          tool_name: null, label: null, path: null,
          status_text: null, active: type === "session.created",
          alert_type: type === "session.idle" ? 0x01 : type === "session.error" ? 0x02 : 0,
          ts: Date.now() / 1000, meta: {},
        });
      }
    },
  };
};
"""


def install_opencode_plugin(project_root: Path | None = None) -> bool:
    """Install the TypeScript plugin globally at ~/.config/opencode/plugins/.

    This makes the plugin available to all OpenCode sessions regardless of
    which project directory they run in.

    Parameters
    ----------
    project_root:
        Ignored (kept for API compatibility). The plugin is always installed
        globally.

    Returns
    -------
    bool
        True if the plugin was installed; False if OpenCode is not detected.
    """
    if not is_opencode_installed():
        logger.info("OpenCode not detected — skipping plugin installation")
        return False

    _OPENCODE_GLOBAL_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _OPENCODE_GLOBAL_PLUGINS_DIR / OPENCODE_PLUGIN_FILENAME

    # Remove superseded plugin filename from prior project name.
    legacy_global = _OPENCODE_GLOBAL_PLUGINS_DIR / "claude_garmin_opencode.ts"
    if legacy_global.exists():
        legacy_global.unlink()
        logger.info("Removed legacy OpenCode plugin at {}", legacy_global)

    source = _get_plugin_source()
    _atomic_write_text(dest, source)
    logger.info("OpenCode plugin installed globally at {}", dest)
    return True


def _normalise_plugin_array(config: dict) -> list[str]:
    """Return a writable `plugin` array, migrating legacy shapes when needed."""
    raw_plugins = config.get("plugin")

    if isinstance(raw_plugins, list):
        plugins = [p for p in raw_plugins if isinstance(p, str) and p]
        if len(plugins) != len(raw_plugins):
            logger.warning(
                "Ignoring non-string entries in opencode.json 'plugin' array"
            )
        # De-duplicate while preserving order
        config["plugin"] = list(dict.fromkeys(plugins))
        return config["plugin"]

    migrated: list[str] = []
    legacy_plugins = config.get("plugins")
    if isinstance(legacy_plugins, list):
        for entry in legacy_plugins:
            if isinstance(entry, str) and entry:
                migrated.append(entry)
                continue
            if isinstance(entry, dict):
                path_val = entry.get("path")
                if isinstance(path_val, str) and path_val:
                    migrated.append(path_val)
        if migrated:
            logger.info(
                "Migrated {} plugin path(s) from legacy 'plugins' key",
                len(migrated),
            )

    config["plugin"] = list(dict.fromkeys(migrated))
    return config["plugin"]


def _patch_opencode_json(project_root: Path) -> None:
    """Add the oh-my-wrist plugin entry to .opencode/opencode.json."""
    config_path = project_root / ".opencode" / "opencode.json"

    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                logger.warning("opencode.json root is not an object — creating fresh")
                config = {}
        except json.JSONDecodeError:
            logger.warning("opencode.json is not valid JSON — creating fresh")
            config = {}
    else:
        config = {}

    plugins = _normalise_plugin_array(config)

    if _OPENCODE_PLUGIN_ENTRY in plugins:
        logger.info("OpenCode plugin already registered in opencode.json")
        return

    plugins.append(_OPENCODE_PLUGIN_ENTRY)
    _atomic_write_json(config_path, config)
    logger.info("OpenCode plugin registered in {}", config_path)


def remove_opencode_plugin(project_root: Path | None = None) -> bool:
    """Remove the TypeScript plugin from the global plugins directory.

    Also cleans up any legacy per-project installation if found.

    Returns True if removal was performed, False if nothing to remove.
    """
    removed = False

    # Remove from global location
    global_path = _OPENCODE_GLOBAL_PLUGINS_DIR / OPENCODE_PLUGIN_FILENAME
    if global_path.exists():
        global_path.unlink()
        logger.info("OpenCode plugin removed from {}", global_path)
        removed = True

    # Clean up legacy per-project installation if present
    root = project_root or find_opencode_project_root()
    if root is not None:
        legacy_path = root / ".opencode" / "plugins" / OPENCODE_PLUGIN_FILENAME
        if legacy_path.exists():
            legacy_path.unlink()
            logger.info("Legacy per-project plugin removed from {}", legacy_path)
            removed = True

        # Remove from opencode.json if present
        config_path = root / ".opencode" / "opencode.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(config, dict):
                    plugins = config.get("plugin")
                    if isinstance(plugins, list):
                        new_plugins = [
                            p for p in plugins if p != _OPENCODE_PLUGIN_ENTRY
                        ]
                        if len(new_plugins) != len(plugins):
                            config["plugin"] = new_plugins
                            _atomic_write_json(config_path, config)
                            logger.info("Plugin entry removed from {}", config_path)
            except json.JSONDecodeError:
                pass

    return removed


# ---------------------------------------------------------------------------
# Combined install / uninstall
# ---------------------------------------------------------------------------


def install_all(provider: str = "both", project_root: Path | None = None) -> None:
    """Install hooks/plugins for the specified provider(s).

    Parameters
    ----------
    provider:
        ``"claude"`` — Claude Code only.
        ``"opencode"`` — OpenCode only.
        ``"both"`` (default) — both providers.
    """
    if provider in ("claude", "both"):
        patch_claude_settings()

    if provider in ("opencode", "both"):
        install_opencode_plugin(project_root)

    install_service()
    logger.info("Installation complete (provider={})", provider)


def uninstall_all(provider: str = "both", project_root: Path | None = None) -> None:
    """Remove hooks/plugins for the specified provider(s)."""
    if provider in ("claude", "both"):
        remove_claude_hooks()

    if provider in ("opencode", "both"):
        remove_opencode_plugin(project_root)

    uninstall_service()
    logger.info("Uninstallation complete (provider={})", provider)


# ---------------------------------------------------------------------------
# Service registration (platform dispatch)
# ---------------------------------------------------------------------------


def install_service() -> None:
    """Register the BLE daemon as a system service for the current platform."""
    if sys.platform == "darwin":
        from ohm.platform.macos import install_service as _install
    elif sys.platform == "win32":
        from ohm.platform.windows import install_service as _install  # type: ignore[assignment]
    else:
        from ohm.platform.linux import install_service as _install  # type: ignore[assignment]
    _install()
    logger.info("System service registered")


def uninstall_service() -> None:
    """Remove the system service registration."""
    if sys.platform == "darwin":
        from ohm.platform.macos import uninstall_service as _uninstall
    elif sys.platform == "win32":
        from ohm.platform.windows import uninstall_service as _uninstall  # type: ignore[assignment]
    else:
        from ohm.platform.linux import uninstall_service as _uninstall  # type: ignore[assignment]
    _uninstall()
    logger.info("System service removed")


def get_service_status() -> str:
    """Return a human-readable service status string."""
    if sys.platform == "darwin":
        from ohm.platform.macos import service_status
    elif sys.platform == "win32":
        from ohm.platform.windows import service_status  # type: ignore[assignment]
    else:
        from ohm.platform.linux import service_status  # type: ignore[assignment]
    return service_status()

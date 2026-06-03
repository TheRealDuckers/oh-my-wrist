/**
 * oh_my_wrist_opencode.ts — OpenCode plugin for oh-my-wrist.
 *
 * Bridges OpenCode session/tool activity to the oh-my-wrist BLE daemon by
 * translating each meaningful OpenCode signal into a CanonicalIpcMessage and
 * shipping it over a local Unix domain socket (or named pipe on Windows).
 *
 * Hook channels used (per https://opencode.ai/docs/plugins):
 *
 *   1. `tool.execute.before` — fires before a tool runs. Emits `tool_start`.
 *   2. `tool.execute.after`  — fires after a tool runs. Emits `tool_end`.
 *   3. `event`               — generic bus subscription. Handles session.*,
 *                              permission.*, file.edited, todo.updated,
 *                              command.executed events.
 *
 * Wire format: one JSON object per IPC line, matching CanonicalIpcMessage in
 * src/ohm/protocol.py.
 */

import * as net from "net";
import * as os from "os";
import * as path from "path";

// ---------------------------------------------------------------------------
// IPC transport
// ---------------------------------------------------------------------------

const IS_WINDOWS = process.platform === "win32";

function unixSocketPath(): string {
  const uid = typeof process.getuid === "function"
    ? process.getuid()
    : os.userInfo().uid;
  return path.join("/tmp", `oh-my-wrist-${uid}`, "ohm.sock");
}

const SOCKET_PATH = IS_WINDOWS
  ? String.raw`\\.\pipe\ohm`
  : unixSocketPath();

async function sendToDaemon(payload: object): Promise<void> {
  const json = JSON.stringify(payload) + "\n";
  return new Promise<void>((resolve) => {
    try {
      const sock = net.createConnection(SOCKET_PATH);
      sock.on("connect", () => {
        sock.write(json, "utf8", () => {
          sock.end();
          resolve();
        });
      });
      sock.on("error", () => resolve());
      sock.setTimeout(500, () => {
        sock.destroy();
        resolve();
      });
    } catch {
      resolve();
    }
  });
}

// ---------------------------------------------------------------------------
// Alert type constants (must match protocol.py)
// ---------------------------------------------------------------------------

const ALERT_NONE = 0x00;
const ALERT_IDLE_WAITING = 0x01;
const ALERT_SESSION_DONE = 0x02;
const ALERT_DESTRUCTIVE = 0x03;
const ALERT_AGENT_DONE = 0x04;

// ---------------------------------------------------------------------------
// Bus event allowlist
// ---------------------------------------------------------------------------

const BUS_ALLOW = new Set([
  "session.created",
  "session.idle",
  "session.completed",
  "session.status",
  "session.error",
  "permission.updated",
  "permission.replied",
  "file.edited",
  "todo.updated",
  "command.executed",
]);

// ---------------------------------------------------------------------------
// Canonical event / provider_event constants
// ---------------------------------------------------------------------------

const PE_TOOL_START = "tool.execute.before";
const PE_TOOL_END = "tool.execute.after";
const PE_SESSION_START = "session.created";
const PE_SESSION_IDLE = "session.idle";
const PE_SESSION_ERROR = "session.error";
const PE_SESSION_STOP = "session.completed";
const PE_PERMISSION_REQUEST = "permission.updated";
const PE_PERMISSION_REPLY = "permission.replied";
const PE_FILE_EDIT = "file.edited";
const PE_TODO_UPDATE = "todo.updated";
const PE_COMMAND = "command.executed";

const CE_TOOL_START = "tool_start";
const CE_TOOL_END = "tool_end";
const CE_SESSION_START = "session_start";
const CE_SESSION_IDLE = "session_idle";
const CE_SESSION_ERROR = "session_error";
const CE_SESSION_STOP = "session_stop";
const CE_PERMISSION_REQUEST = "permission_request";
const CE_PERMISSION_REPLY = "permission_reply";
const CE_FILE_EDIT = "file_edit";
const CE_TODO_UPDATE = "todo_update";
const CE_COMMAND = "command";

// ---------------------------------------------------------------------------
// Tool intent groups (mirrors provider_types.py TOOL_INTENT)
// ---------------------------------------------------------------------------

const AGENT_TOOLS = new Set([
  "agent", "subagent", "task", "dispatch",
]);

const SHELL_TOOLS = new Set([
  "bash", "shell", "run", "command", "exec", "execute", "terminal",
]);

const DESTRUCTIVE_RE =
  /\brm\b|\brmdir\b|\bDROP\b|\bTRUNCATE\b|--force\b|\bformat\b|\bmkfs\b|\bdd\b.*of=|\bshred\b|\bchmod\s+777\b|\bkill\s+-9\b|>\s*\/dev\//i;

function isDestructiveCommand(toolName: string | null, args: Record<string, unknown>): boolean {
  if (!toolName || !SHELL_TOOLS.has(toolName.toLowerCase())) return false;
  const cmd = String(args?.command ?? args?.cmd ?? "");
  return DESTRUCTIVE_RE.test(cmd);
}

// ---------------------------------------------------------------------------
// String hygiene
// ---------------------------------------------------------------------------

const ANSI_RE = /\x1b\[[0-9;]*[A-Za-z]|\x1b\[[0-9;]*m|\x1b\].*?\x07/g;
const CTRL_RE = /[\x00-\x08\x0b-\x1f\x7f]/g;

function clean(text: string | null | undefined): string | null {
  if (!text) return null;
  return text
    .replace(ANSI_RE, "")
    .replace(CTRL_RE, "")
    .replace(/\s+/g, " ")
    .trim() || null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

// ---------------------------------------------------------------------------
// Label / path derivation
// ---------------------------------------------------------------------------

function deriveLabel(toolName: string | null, args: Record<string, unknown>): string | null {
  if (toolName && SHELL_TOOLS.has(toolName.toLowerCase())) {
    return clean(String(args?.command ?? args?.cmd ?? ""));
  }
  const p = asString(args?.path) ?? asString(args?.file_path) ?? asString(args?.filePath) ?? asString(args?.filename);
  if (p) return p;
  return toolName;
}

function derivePath(args: Record<string, unknown>): string | null {
  return (
    asString(args?.path) ??
    asString(args?.file_path) ??
    asString(args?.filePath) ??
    asString(args?.filename) ??
    null
  );
}

// ---------------------------------------------------------------------------
// Alert computation
// ---------------------------------------------------------------------------

function alertForToolStart(toolName: string | null, args: Record<string, unknown>): number {
  return isDestructiveCommand(toolName, args) ? ALERT_DESTRUCTIVE : ALERT_NONE;
}

function alertForToolEnd(toolName: string | null): number {
  if (toolName && AGENT_TOOLS.has(toolName.toLowerCase())) return ALERT_AGENT_DONE;
  return ALERT_NONE;
}

// ---------------------------------------------------------------------------
// Emit helper — constructs and sends a CanonicalIpcMessage
// ---------------------------------------------------------------------------

interface Emit {
  providerEvent: string;
  canonicalEvent: string;
  sessionId?: string | null;
  toolName?: string | null;
  label?: string | null;
  path?: string | null;
  statusText?: string | null;
  active?: boolean;
  alertType?: number;
  meta?: Record<string, unknown>;
}

async function emit(args: Emit): Promise<void> {
  const payload = {
    provider: "opencode",
    provider_event: args.providerEvent,
    canonical_event: args.canonicalEvent,
    session_id: args.sessionId ?? null,
    tool_name: args.toolName ?? null,
    label: args.label ?? null,
    path: args.path ?? null,
    status_text: args.statusText ?? null,
    active: args.active !== false,
    alert_type: args.alertType ?? ALERT_NONE,
    ts: Date.now() / 1000,
    meta: args.meta ?? {},
  };
  await sendToDaemon(payload);
}

// ---------------------------------------------------------------------------
// Bus event handler
// ---------------------------------------------------------------------------

async function handleBusEvent(event: unknown): Promise<void> {
  const evt = asRecord(event);
  if (!evt) return;

  const type = asString(evt.type);
  if (!type || !BUS_ALLOW.has(type)) return;

  const properties = asRecord(evt.properties) ?? {};
  const sessionId =
    asString(evt.sessionId) ??
    asString(properties.sessionID) ??
    asString(properties.sessionId) ??
    asString(asRecord(properties.info)?.id) ??    // session.created: properties.info.id
    asString(asRecord(properties.session)?.id) ??
    null;

  switch (type) {
    case "session.created":
      await emit({
        providerEvent: PE_SESSION_START,
        canonicalEvent: CE_SESSION_START,
        sessionId,
        meta: properties,
      });
      return;

    case "session.idle":
      await emit({
        providerEvent: PE_SESSION_IDLE,
        canonicalEvent: CE_SESSION_IDLE,
        sessionId,
        active: false,
        alertType: ALERT_IDLE_WAITING,
        meta: properties,
      });
      return;

    case "session.completed":
      await emit({
        providerEvent: PE_SESSION_STOP,
        canonicalEvent: CE_SESSION_STOP,
        sessionId,
        active: false,
        alertType: ALERT_SESSION_DONE,
        meta: properties,
      });
      return;

    case "session.status": {
      const statusType = asString(asRecord(properties.status)?.type);
      if (statusType === "idle") {
        await emit({
          providerEvent: PE_SESSION_IDLE,
          canonicalEvent: CE_SESSION_IDLE,
          sessionId,
          active: false,
          alertType: ALERT_IDLE_WAITING,
          meta: properties,
        });
      } else if (statusType === "completed") {
        await emit({
          providerEvent: PE_SESSION_STOP,
          canonicalEvent: CE_SESSION_STOP,
          sessionId,
          active: false,
          alertType: ALERT_SESSION_DONE,
          meta: properties,
        });
      }
      return;
    }

    case "session.error": {
      const errorMsg = asString(asRecord(properties.error)?.name) ?? asString(properties.message);
      await emit({
        providerEvent: PE_SESSION_ERROR,
        canonicalEvent: CE_SESSION_ERROR,
        sessionId,
        statusText: clean(errorMsg),
        active: false,
        alertType: ALERT_SESSION_DONE,
        meta: properties,
      });
      return;
    }

    case "permission.updated": {
      const message =
        asString(properties.title) ??
        asString(properties.message) ??
        asString(properties.description) ??
        asString(asRecord(properties.permission)?.title) ??
        asString(asRecord(properties.permission)?.message);
      await emit({
        providerEvent: PE_PERMISSION_REQUEST,
        canonicalEvent: CE_PERMISSION_REQUEST,
        sessionId,
        label: clean(message),
        alertType: ALERT_IDLE_WAITING,
        meta: properties,
      });
      return;
    }

    case "permission.replied": {
      await emit({
        providerEvent: PE_PERMISSION_REPLY,
        canonicalEvent: CE_PERMISSION_REPLY,
        sessionId,
        active: false,
        meta: properties,
      });
      return;
    }

    case "file.edited": {
      // EventFileEdited.properties = { file: string }
      const filePath = asString(properties.file) ?? asString(properties.path) ?? asString(properties.filePath);
      await emit({
        providerEvent: PE_FILE_EDIT,
        canonicalEvent: CE_FILE_EDIT,
        sessionId,
        label: filePath,
        path: filePath,
        meta: properties,
      });
      return;
    }

    case "todo.updated":
      await emit({
        providerEvent: PE_TODO_UPDATE,
        canonicalEvent: CE_TODO_UPDATE,
        sessionId,
        meta: properties,
      });
      return;

    case "command.executed": {
      // EventCommandExecuted.properties = { name, sessionID, arguments, messageID }
      const cmd = asString(properties.name) ?? asString(properties.command) ?? asString(properties.cmd);
      await emit({
        providerEvent: PE_COMMAND,
        canonicalEvent: CE_COMMAND,
        sessionId,
        label: clean(cmd),
        meta: properties,
      });
      return;
    }
  }
}

// ---------------------------------------------------------------------------
// Plugin registration — named export per OpenCode plugin API
// ---------------------------------------------------------------------------

const OhMyWristPlugin = async (_ctx: unknown) => {
  return {
    "tool.execute.before": async (input: unknown, output: unknown) => {
      const inputRec = asRecord(input) ?? {};
      const outputRec = asRecord(output) ?? {};
      const args = asRecord(outputRec.args) ?? asRecord(inputRec.args) ?? {};

      const toolName = asString(inputRec.tool) ?? asString(inputRec.toolName);
      const sessionId =
        asString(inputRec.sessionID) ??
        asString(inputRec.sessionId) ??
        null;

      await emit({
        providerEvent: PE_TOOL_START,
        canonicalEvent: CE_TOOL_START,
        sessionId,
        toolName,
        label: deriveLabel(toolName, args),
        path: derivePath(args),
        alertType: alertForToolStart(toolName, args),
        meta: { args },
      });
    },

    "tool.execute.after": async (input: unknown, output: unknown) => {
      const inputRec = asRecord(input) ?? {};
      const outputRec = asRecord(output) ?? {};
      const args = asRecord(outputRec.args) ?? asRecord(inputRec.args) ?? {};

      const toolName = asString(inputRec.tool) ?? asString(inputRec.toolName);
      const sessionId =
        asString(inputRec.sessionID) ??
        asString(inputRec.sessionId) ??
        null;

      await emit({
        providerEvent: PE_TOOL_END,
        canonicalEvent: CE_TOOL_END,
        sessionId,
        toolName,
        label: deriveLabel(toolName, args),
        path: derivePath(args),
        active: false,
        alertType: alertForToolEnd(toolName),
        meta: { args },
      });
    },

    event: async ({ event }: { event: unknown }) => {
      await handleBusEvent(event);
    },
  };
};

// Default export — required by OpenCode's plugin loader.
//
// IMPORTANT: do NOT add additional named exports below. OpenCode's plugin
// loader iterates over every export of the module and invokes each one as a
// plugin factory. Any extra exported value either crashes ("Plugin export is
// not a function" for non-functions like Sets/objects) or gets called with
// the plugin context (corrupting internal helpers). Keep helpers file-local.
export default OhMyWristPlugin;

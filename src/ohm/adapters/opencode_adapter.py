"""
opencode_adapter.py — Converts OpenCode plugin events into CanonicalEvent.

The OpenCode TypeScript plugin sends compact JSON over the local IPC socket.
This adapter validates and normalises those payloads into the provider-agnostic
CanonicalEvent consumed by the rest of the pipeline.

OpenCode event → Canonical mapping
------------------------------------
tool.execute.before     → tool_start
tool.execute.after      → tool_end
session.created         → session_start
session.idle            → session_idle
session.status          → status  (or ignored if redundant)
session.error           → session_error
session.updated         → status  (debounced / may be suppressed)
file.edited             → file_edit
todo.updated            → todo_update
permission.asked        → permission_request
permission.updated      → permission_request  (SDK v1 naming)
permission.replied      → permission_reply
command.executed        → command
(anything else)         → unknown

Noise control
-------------
- ``session.updated`` events are suppressed unless ``status_text`` differs
  from the last seen status for the same session.
- Rapid identical ``tool.execute.before`` events within DEBOUNCE_WINDOW_S
  seconds are coalesced (only the first is forwarded).
"""

from __future__ import annotations

import re
import time
from typing import Any

from ohm.provider_types import CanonicalEvent, CanonicalEventType

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Seconds within which identical (session_id, provider_event, label) tuples
# are suppressed as duplicates.
DEBOUNCE_WINDOW_S: float = 0.5

# ---------------------------------------------------------------------------
# Event mapping
# ---------------------------------------------------------------------------

_OC_EVENT_MAP: dict[str, CanonicalEventType] = {
    "tool.execute.before": "tool_start",
    "tool.execute.after": "tool_end",
    "session.created": "session_start",
    "session.idle": "session_idle",
    "session.status": "status",
    "session.completed": "session_stop",
    "session.error": "session_error",
    "session.updated": "status",
    "file.edited": "file_edit",
    "todo.updated": "todo_update",
    "permission.asked": "permission_request",
    "permission.updated": "permission_request",
    "permission.replied": "permission_reply",
    "command.executed": "command",
}

# ---------------------------------------------------------------------------
# ANSI / control-character stripping
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\[[0-9;]*m|\x1b\].*?\x07")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _clean(text: str) -> str:
    """Strip ANSI escape codes, control characters, and collapse whitespace."""
    text = _ANSI_RE.sub("", text)
    text = _CTRL_RE.sub("", text)
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# Debounce state (module-level, lightweight)
# ---------------------------------------------------------------------------

# Maps (session_id, provider_event, label) → last_seen_ts
_debounce_cache: dict[tuple, float] = {}


def _is_debounced(
    session_id: str | None, provider_event: str, label: str | None
) -> bool:
    """Return True if this event should be suppressed due to debounce."""
    key = (session_id, provider_event, label)
    now = time.time()
    last = _debounce_cache.get(key, 0.0)
    if now - last < DEBOUNCE_WINDOW_S:
        return True
    _debounce_cache[key] = now
    return False


def clear_debounce_cache() -> None:
    """Clear the debounce cache (useful in tests)."""
    _debounce_cache.clear()


# ---------------------------------------------------------------------------
# Session-updated suppression state
# ---------------------------------------------------------------------------

# Maps session_id → last forwarded status_text
_last_status: dict[str | None, str] = {}


def _should_suppress_session_updated(
    session_id: str | None, status_text: str | None
) -> bool:
    """Suppress session.updated if status_text has not changed."""
    if status_text is None:
        return True
    if _last_status.get(session_id) == status_text:
        return True
    _last_status[session_id] = status_text
    return False


def clear_status_cache() -> None:
    """Clear the session-updated suppression cache (useful in tests)."""
    _last_status.clear()


# ---------------------------------------------------------------------------
# Main adapter
# ---------------------------------------------------------------------------


def adapt_opencode_event(payload: dict[str, Any]) -> CanonicalEvent | None:
    """Convert a raw OpenCode plugin JSON payload into a :class:`CanonicalEvent`.

    Returns ``None`` if the event should be suppressed (noise control).

    Parameters
    ----------
    payload:
        The raw dict received from the OpenCode plugin over IPC.  Expected
        keys are documented in Section 12.2 of the spec.
    """
    provider_event: str = payload.get("provider_event", payload.get("event", ""))
    canonical: CanonicalEventType = _OC_EVENT_MAP.get(provider_event, "unknown")

    # Defense in depth: drop unknown events at the adapter so a stale or
    # broken plugin can never flood the watch with "? message.updated" /
    # "? session.diff" noise. The new TS plugin already filters via an
    # allowlist; this is a second seam in case an older plugin build is
    # still installed.
    if canonical == "unknown":
        return None

    session_id: str | None = payload.get("session_id")
    tool_name: str | None = payload.get("tool_name")
    path: str | None = payload.get("path")
    raw_label: str | None = payload.get("label")
    status_text: str | None = payload.get("status_text")
    meta: dict = payload.get("meta", {})
    ts: float = float(payload.get("ts", time.time()))
    active: bool = bool(payload.get("active", True))

    # Clean label and status_text
    label = _clean(raw_label) if raw_label else None
    if status_text:
        status_text = _clean(status_text)

    # -----------------------------------------------------------------------
    # Noise control
    # -----------------------------------------------------------------------

    # Suppress redundant session.updated
    if provider_event == "session.updated":
        if _should_suppress_session_updated(session_id, status_text or label):
            return None

    # Debounce rapid identical tool.execute.before events
    if provider_event == "tool.execute.before":
        if _is_debounced(session_id, provider_event, label):
            return None

    # -----------------------------------------------------------------------
    # Derive path from meta if not top-level
    # -----------------------------------------------------------------------
    if path is None and meta:
        path = meta.get("path") or meta.get("file") or meta.get("filename")

    # -----------------------------------------------------------------------
    # Derive label from meta for file/command events
    # -----------------------------------------------------------------------
    if label is None:
        if canonical == "file_edit" and path:
            label = path
        elif canonical == "command":
            label = meta.get("command") or meta.get("cmd")
        elif canonical == "permission_request":
            label = meta.get("title") or meta.get("message") or meta.get("description")
        elif canonical == "permission_reply":
            approved = meta.get("approved", meta.get("decision"))
            label = "approved" if approved else "denied"

    return CanonicalEvent(
        provider="opencode",
        provider_event=provider_event,
        canonical_event=canonical,
        session_id=session_id,
        tool_name=tool_name,
        label=label,
        path=path,
        status_text=status_text,
        active=active,
        ts=ts,
        meta=meta,
    )

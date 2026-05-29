"""
session_tracker.py — Accumulates per-session statistics from IPC messages.

The tracker is instantiated once by the BLE daemon and updated on every
incoming HookMessage.  It produces a compact JSON payload (≤ 100 bytes)
that is pushed to the watch via STATS_CHAR_UUID.

Payload format
--------------
{"d":312,"t":47,"e":9,"b":23,"i":45,"c":"2m ago"}

Key  Meaning                              Type
---  -----------------------------------  ----
d    Session duration in seconds          int
t    Total tool calls (PreToolUse count)  int
e    Unique files edited (Edit/Write)     int
b    Bash commands run                    int
i    Total idle seconds (Notification)   int
c    Time since last session completion   str (max 8 chars)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import time
from typing import Optional

from ohm.protocol import MAX_STATS_LEN


@dataclass
class SessionStats:
    """Mutable per-session statistics accumulator."""

    start_time: float = field(default_factory=time)
    tool_calls: int = 0
    edited_files: set = field(default_factory=set)
    bash_count: int = 0
    idle_seconds: float = 0.0
    last_idle_start: Optional[float] = None
    last_completion_time: Optional[float] = None

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def on_message(self, msg) -> None:  # msg: IpcMessage / HookMessage
        """Update statistics from a single IPC message.

        Parameters
        ----------
        msg:
            An :class:`~ohm.protocol.IpcMessage` (or compatible
            object with ``.event`` and ``.event_data`` attributes).
        """
        # Every message counts as a tool-call-equivalent activity
        self.tool_calls += 1

        event = getattr(msg, "event", "")
        event_data = getattr(msg, "event_data", {}) or {}

        if event == "PreToolUse":
            tool = event_data.get("tool_name", "")
            if tool in ("Edit", "Write", "MultiEdit"):
                path = (event_data.get("tool_input") or {}).get("path", "")
                if path:
                    self.edited_files.add(path)
            if tool == "Bash":
                self.bash_count += 1

        # Start idle timer on Notification
        if event == "Notification":
            if self.last_idle_start is None:
                self.last_idle_start = time()

        # Stop idle timer when activity resumes
        if event in ("PreToolUse", "PostToolUse", "Stop"):
            if self.last_idle_start is not None:
                self.idle_seconds += time() - self.last_idle_start
                self.last_idle_start = None

        if event == "Stop":
            self.last_completion_time = time()

    def reset(self) -> None:
        """Reset all counters to their initial state (new session)."""
        self.__init__()  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_ble_payload(self) -> bytes:
        """Serialise current stats to a compact UTF-8 JSON byte string.

        The result is guaranteed to be at most MAX_STATS_LEN (100) bytes.
        """
        now = time()
        duration = int(now - self.start_time)

        # Compute idle including any currently-open idle window
        idle = self.idle_seconds
        if self.last_idle_start is not None:
            idle += now - self.last_idle_start

        if self.last_completion_time is not None:
            delta = int(now - self.last_completion_time)
            if delta < 60:
                c = f"{delta}s ago"
            else:
                c = f"{delta // 60}m ago"
        else:
            c = "never"

        payload = json.dumps(
            {
                "d": duration,
                "t": self.tool_calls,
                "e": len(self.edited_files),
                "b": self.bash_count,
                "i": int(idle),
                "c": c[:8],
            },
            separators=(",", ":"),
        )
        encoded = payload.encode("utf-8")

        # Safety truncation (should never trigger in practice)
        if len(encoded) > MAX_STATS_LEN:
            encoded = encoded[:MAX_STATS_LEN]

        return encoded

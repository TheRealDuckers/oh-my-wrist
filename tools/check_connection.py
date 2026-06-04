#!/usr/bin/env python3
"""Send a short diagnostic event stream to a running oh-my-wrist daemon.

This exercises the normal IPC -> daemon -> BLE path so users can confirm the
watch app is receiving HISTORY frames, per-provider stats, and Claude usage
updates. It does not talk to Bluetooth directly.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

# Ensure the project source is importable when run from a source checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ohm.protocol import (  # noqa: E402
    ALERT_IDLE_WAITING,
    ALERT_NONE,
    ALERT_SESSION_DONE,
    CanonicalIpcMessage,
    send_to_daemon,
)

ProviderName = str


def _message(
    *,
    provider: ProviderName,
    provider_event: str,
    canonical_event: str,
    ts: float,
    offset: float,
    session_id: str,
    tool_name: str | None = None,
    label: str | None = None,
    path: str | None = None,
    status_text: str | None = None,
    active: bool = True,
    alert_type: int = ALERT_NONE,
    meta: dict | None = None,
) -> CanonicalIpcMessage:
    return CanonicalIpcMessage(
        provider=provider,
        provider_event=provider_event,
        canonical_event=canonical_event,
        session_id=session_id,
        tool_name=tool_name,
        label=label,
        path=path,
        status_text=status_text,
        active=active,
        alert_type=alert_type,
        ts=ts + offset,
        meta=meta or {},
    )


def _claude_messages(now: float) -> list[CanonicalIpcMessage]:
    session_id = f"check-claude-{int(now)}"
    return [
        _message(
            provider="claude",
            provider_event="SessionStart",
            canonical_event="session_start",
            ts=now,
            offset=0,
            session_id=session_id,
            label="connection check",
            status_text="connection check",
        ),
        _message(
            provider="claude",
            provider_event="PreToolUse",
            canonical_event="tool_start",
            ts=now,
            offset=1,
            session_id=session_id,
            tool_name="Bash",
            label="pytest tests",
            meta={"command": "pytest tests"},
        ),
        _message(
            provider="claude",
            provider_event="PostToolUse",
            canonical_event="tool_end",
            ts=now,
            offset=2,
            session_id=session_id,
            tool_name="Bash",
            label="pytest tests",
        ),
        _message(
            provider="claude",
            provider_event="PostToolUse",
            canonical_event="file_edit",
            ts=now,
            offset=3,
            session_id=session_id,
            tool_name="Edit",
            label="check_connection.py",
            path="tools/check_connection.py",
        ),
        _message(
            provider="claude",
            provider_event="TodoWrite",
            canonical_event="todo_update",
            ts=now,
            offset=4,
            session_id=session_id,
            tool_name="TodoWrite",
            label="connection checklist",
        ),
        _message(
            provider="claude",
            provider_event="statusline",
            canonical_event="usage",
            ts=now,
            offset=5,
            session_id=session_id,
            active=False,
            meta={"s": 42, "w": 17},
        ),
        _message(
            provider="claude",
            provider_event="Notification",
            canonical_event="session_idle",
            ts=now,
            offset=6,
            session_id=session_id,
            label="waiting",
            alert_type=ALERT_IDLE_WAITING,
        ),
        _message(
            provider="claude",
            provider_event="Stop",
            canonical_event="session_stop",
            ts=now,
            offset=7,
            session_id=session_id,
            active=False,
            alert_type=ALERT_SESSION_DONE,
        ),
    ]


def _opencode_messages(now: float) -> list[CanonicalIpcMessage]:
    session_id = f"check-opencode-{int(now)}"
    return [
        _message(
            provider="opencode",
            provider_event="session.start",
            canonical_event="session_start",
            ts=now,
            offset=0,
            session_id=session_id,
            label="connection check",
            status_text="connection check",
        ),
        _message(
            provider="opencode",
            provider_event="tool.execute.before",
            canonical_event="tool_start",
            ts=now,
            offset=1,
            session_id=session_id,
            tool_name="edit",
            label="demo.py",
            path="demo.py",
        ),
        _message(
            provider="opencode",
            provider_event="tool.execute.after",
            canonical_event="tool_end",
            ts=now,
            offset=2,
            session_id=session_id,
            tool_name="edit",
            label="demo.py",
            path="demo.py",
        ),
        _message(
            provider="opencode",
            provider_event="tool.execute.before",
            canonical_event="tool_start",
            ts=now,
            offset=3,
            session_id=session_id,
            tool_name="shell",
            label="git status",
            meta={"command": "git status"},
        ),
        _message(
            provider="opencode",
            provider_event="tool.execute.after",
            canonical_event="tool_end",
            ts=now,
            offset=4,
            session_id=session_id,
            tool_name="shell",
            label="git status",
        ),
        _message(
            provider="opencode",
            provider_event="session.idle",
            canonical_event="session_idle",
            ts=now,
            offset=5,
            session_id=session_id,
            label="waiting",
            alert_type=ALERT_IDLE_WAITING,
        ),
        _message(
            provider="opencode",
            provider_event="session.end",
            canonical_event="session_stop",
            ts=now,
            offset=6,
            session_id=session_id,
            active=False,
            alert_type=ALERT_SESSION_DONE,
        ),
    ]


def build_messages(
    providers: Sequence[ProviderName] = ("claude", "opencode"),
    *,
    now: float | None = None,
) -> list[CanonicalIpcMessage]:
    """Build one diagnostic cycle for the selected providers."""
    ts = time.time() if now is None else now
    selected = tuple(providers)
    messages: list[CanonicalIpcMessage] = []

    if "claude" in selected:
        messages.extend(_claude_messages(ts))
    if "opencode" in selected:
        messages.extend(_opencode_messages(ts))

    return messages


def _describe(msg: CanonicalIpcMessage) -> str:
    label = msg.label or msg.status_text or msg.path or ""
    if msg.canonical_event == "usage":
        label = f"s={msg.meta.get('s')}% w={msg.meta.get('w')}%"
    suffix = f" {label}" if label else ""
    return f"{msg.provider:8s} {msg.canonical_event:13s}{suffix}"


async def send_cycle(
    messages: Sequence[CanonicalIpcMessage],
    *,
    interval: float,
    dry_run: bool,
) -> None:
    """Send one message cycle, optionally only printing what would be sent."""
    for index, msg in enumerate(messages, start=1):
        await _send_message(msg, index=index, total=len(messages), dry_run=dry_run)
        if interval > 0 and index < len(messages):
            await asyncio.sleep(interval)


async def _send_message(
    msg: CanonicalIpcMessage,
    *,
    index: int,
    total: int,
    dry_run: bool,
) -> None:
    action = "would send" if dry_run else "sent"
    if not dry_run:
        await send_to_daemon(msg)
    print(f"[{index:02d}/{total:02d}] {action}: {_describe(msg)}")


def _final_stop_messages(
    providers: Iterable[ProviderName],
) -> list[CanonicalIpcMessage]:
    now = time.time()
    return [
        _message(
            provider=provider,
            provider_event="diagnostic.stop",
            canonical_event="session_stop",
            ts=now,
            offset=index,
            session_id=f"check-{provider}-{int(now)}",
            active=False,
            alert_type=ALERT_NONE,
        )
        for index, provider in enumerate(providers)
    ]


async def run_diagnostic(
    *,
    duration: float,
    interval: float,
    providers: Sequence[ProviderName],
    dry_run: bool,
) -> None:
    """Run diagnostic cycles for approximately ``duration`` seconds."""
    deadline = time.monotonic() + duration
    cycle = 0

    print("oh-my-wrist connection check")
    print("Watch for changing history rows, stats counts, and Claude usage bars.")
    if dry_run:
        print("dry-run: no IPC messages will be sent")

    while time.monotonic() < deadline:
        cycle += 1
        print(f"\ncycle {cycle}")
        messages = build_messages(providers)
        for index, msg in enumerate(messages, start=1):
            if time.monotonic() >= deadline:
                break
            await _send_message(
                msg,
                index=index,
                total=len(messages),
                dry_run=dry_run,
            )
            remaining = deadline - time.monotonic()
            if remaining > 0 and interval > 0:
                await asyncio.sleep(min(interval, remaining))
        if interval <= 0:
            break

    if not dry_run:
        for msg in _final_stop_messages(providers):
            await send_to_daemon(msg)

    print("\nConnection check complete.")


def _parse_providers(value: str) -> tuple[ProviderName, ...]:
    if value == "both":
        return ("claude", "opencode")
    return (value,)


def _print_prerequisites() -> None:
    print("Prerequisites:", file=sys.stderr)
    print("  - daemon running: oh-my-wrist start --foreground", file=sys.stderr)
    print("  - watch app open", file=sys.stderr)
    print("  - desktop and watch connection IDs match", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send diagnostic oh-my-wrist events to a running daemon.",
    )
    parser.add_argument(
        "--duration",
        "-t",
        type=float,
        default=60.0,
        help="Seconds to run the connection check (default: 60).",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=4.0,
        help="Seconds between diagnostic events (default: 4).",
    )
    parser.add_argument(
        "--provider",
        "-p",
        choices=("claude", "opencode", "both"),
        default="both",
        help="Provider stream to simulate (default: both).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print messages without sending IPC to the daemon.",
    )
    args = parser.parse_args()

    if args.duration <= 0:
        print("Error: --duration must be greater than 0", file=sys.stderr)
        return 2
    if args.interval < 0:
        print("Error: --interval must not be negative", file=sys.stderr)
        return 2

    try:
        asyncio.run(
            run_diagnostic(
                duration=args.duration,
                interval=args.interval,
                providers=_parse_providers(args.provider),
                dry_run=args.dry_run,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        _print_prerequisites()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

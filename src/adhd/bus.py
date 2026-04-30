"""Core business logic for the ADHD coordination bus."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def resolve() -> Path:
    """Return the absolute path to the ADHD bus file.

    Path resolution order:
    1. ADHD_BUS_PATH env var (storage directory prefix, default: ~/.brainxio/adhd/)
    2. ADHD_BUS_SLUG env var (bus name, default: git toplevel basename)
    3. Full path: {ADHD_BUS_PATH}/{ADHD_BUS_SLUG}/bus.jsonl
    """
    base_dir = Path(os.environ.get("ADHD_BUS_PATH", "~/.brainxio/adhd")).expanduser()

    bus_name = os.environ.get("ADHD_BUS_SLUG")
    if not bus_name:
        try:
            toplevel = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            bus_name = Path(toplevel).name
        except subprocess.CalledProcessError:
            bus_name = "default"

    bus_dir = base_dir / bus_name
    bus_dir.mkdir(parents=True, exist_ok=True)
    return bus_dir / "bus.jsonl"


_session_id: str = os.environ.get("ADHD_SESSION_ID", str(uuid.uuid4())[:8])


def session_id() -> str:
    return _session_id


def agent_id() -> str:
    return os.environ.get("ADHD_AGENT_ID") or f"agent-{session_id()}"


def current_branch() -> str:
    try:
        return (
            subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            or "main"
        )
    except Exception:
        return "unknown"


def now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Bus I/O
# ---------------------------------------------------------------------------


def write_message(msg: dict[str, Any]) -> None:
    """Append a message to the bus after validating it."""
    bus_path = resolve()
    with bus_path.open("a") as f:
        f.write(json.dumps(msg, separators=(",", ":")) + "\n")


def read_messages(
    limit: int = 50,
    type_filter: str | None = None,
    topic_filter: str | None = None,
    agent_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Read recent messages from the bus with optional filtering."""
    bus_path = resolve()
    if not bus_path.exists():
        return []

    messages: list[dict[str, Any]] = []
    with bus_path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if type_filter and msg.get("type") != type_filter:
                continue
            if topic_filter and msg.get("topic") != topic_filter:
                continue
            if agent_filter and msg.get("agent_id") != agent_filter:
                continue
            messages.append(msg)

    return messages[-limit:]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(line: str) -> tuple[bool, str]:
    """Return (valid, error_message) for a single bus line."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        return False, f"Invalid JSON: {exc}"

    required = {"timestamp", "session_id", "agent_id", "branch", "type", "topic", "payload"}
    missing = required - set(obj.keys())
    if missing:
        return False, f"Missing fields: {sorted(missing)}"

    if not isinstance(obj.get("payload"), dict):
        return False, "payload must be an object"

    valid_types = {
        "signin",
        "signout",
        "heartbeat",
        "status",
        "schema",
        "dependency",
        "question",
        "answer",
        "event",
        "tool_use",
        "request",
        "response",
    }
    if obj["type"] not in valid_types:
        return False, f"Invalid type: {obj['type']}"

    return True, ""


def validate_bus() -> tuple[bool, str]:
    """Validate every line in the bus file."""
    bus_path = resolve()
    if not bus_path.exists():
        return True, "Bus file does not exist yet"

    for i, line in enumerate(bus_path.open(), 1):
        line = line.strip()
        if not line:
            continue
        ok, err = validate(line)
        if not ok:
            return False, f"Line {i}: {err}"

    return True, "Bus is valid"


# ---------------------------------------------------------------------------
# Supporter management
# ---------------------------------------------------------------------------


def _is_session_alive(msg: dict[str, Any]) -> bool:
    """Check if a session's most recent activity is within the heartbeat window."""
    ts_str = msg.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_str)
    except ValueError:
        return False
    return (datetime.now(UTC) - ts) < timedelta(minutes=20)


def check_supporters() -> list[dict[str, Any]]:
    """Return active supporter sessions (signin/heartbeat with supporter=True in payload).

    A session is considered active if its most recent heartbeat or signin is
    within the last 20 minutes.
    """
    messages = read_messages(limit=500)
    active: dict[str, dict[str, Any]] = {}

    for msg in messages:
        sid = msg.get("session_id")
        if not isinstance(sid, str):
            continue

        if msg.get("type") == "signout":
            active.pop(sid, None)
            continue

        if msg.get("type") in {"signin", "heartbeat"}:
            payload = msg.get("payload") or {}
            if payload.get("supporter") is True:
                active[sid] = msg

    return [
        {
            "session_id": sid,
            "agent_id": msg.get("agent_id", "unknown"),
            "timestamp": msg.get("timestamp", ""),
            "alive": _is_session_alive(msg),
        }
        for sid, msg in active.items()
        if _is_session_alive(msg)
    ]


# ---------------------------------------------------------------------------
# High-level helpers (signin, signout, heartbeat, post, send)
# ---------------------------------------------------------------------------


def signin() -> str:
    """Write a signin message."""
    payload: dict[str, Any] = {}
    if os.environ.get("ADHD_ENABLE_SUPPORTER"):
        payload["supporter"] = True

    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "signin",
            "topic": "agent-lifecycle",
            "payload": payload,
        }
    )
    if payload.get("supporter"):
        return "Signed in as supporter."
    return "Signed in."


def signout() -> str:
    """Write a signout message."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "signout",
            "topic": "agent-lifecycle",
            "payload": {},
        }
    )
    return "Signed out."


def post(
    type_: str,
    topic: str,
    payload: dict[str, Any] | None = None,
    agent_id_override: str | None = None,
    branch_override: str | None = None,
) -> str:
    """Post a generic message to the bus."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id_override or agent_id(),
            "branch": branch_override or current_branch(),
            "type": type_,
            "topic": topic,
            "payload": payload or {},
        }
    )
    return f"Posted {type_} to {topic}."


def send(to: str, message: str, topic: str = "agent-request", type_: str = "request") -> str:
    """Send a message to a specific agent."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": type_,
            "topic": topic,
            "payload": {"recipient": to, "message": message},
        }
    )
    return f"Sent {type_} to {to}."


# ---------------------------------------------------------------------------
# Archival
# ---------------------------------------------------------------------------

MAX_LINES = 10_000
ARCHIVE_KEEP = 2_000


def archive() -> str:
    """Archive old messages when the bus exceeds the size limit."""
    bus_path = resolve()
    if not bus_path.exists():
        return "Bus file does not exist."

    lines = bus_path.read_text().splitlines()
    if len(lines) <= MAX_LINES:
        return f"Bus has {len(lines)} lines. No archive needed."

    archive_lines = lines[:-ARCHIVE_KEEP]
    keep_lines = lines[-ARCHIVE_KEEP:]
    archive_name = f"bus_archive_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.jsonl"
    archive_path = bus_path.with_name(archive_name)
    tmp_path = bus_path.with_name(".bus.jsonl.tmp")

    archive_path.write_text("\n".join(archive_lines) + "\n")
    tmp_path.write_text("\n".join(keep_lines) + "\n")
    tmp_path.replace(bus_path)
    return (
        f"Archived {len(archive_lines)} lines to {archive_path}. Retained {len(keep_lines)} lines."
    )

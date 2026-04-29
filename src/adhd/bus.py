"""Core business logic for the ADHD coordination bus."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def resolve() -> Path:
    """Return the absolute path to the ADHD bus file."""
    explicit = os.environ.get("ADHD_BUS_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()

    repo_slug = os.environ.get("ADHD_BUS_REPO_SLUG")
    if not repo_slug:
        try:
            toplevel = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            repo_slug = Path(toplevel).name
        except subprocess.CalledProcessError:
            repo_slug = "default"

    bus_dir = Path.home() / ".brainxio" / "adhd" / repo_slug
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
        "main_session_set",
        "main_session_released",
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
# Main session management
# ---------------------------------------------------------------------------


@dataclass
class ClaimResult:
    success: bool
    message: str


def check_main() -> str | None:
    """Return the current main session agent_id, or None."""
    messages = read_messages(limit=200, topic_filter="coordination")
    for msg in reversed(messages):
        if msg.get("type") == "main_session_set":
            return msg.get("agent_id")
        if msg.get("type") == "main_session_released":
            return None
    return None


def get_last_heartbeat(agent: str) -> datetime | None:
    """Return the most recent heartbeat timestamp for an agent."""
    messages = read_messages(
        limit=200,
        type_filter="heartbeat",
        agent_filter=agent,
    )
    if not messages:
        return None
    ts = messages[-1].get("timestamp", "")
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def claim_main(agent_id_str: str | None = None, session_id_str: str | None = None) -> ClaimResult:
    """Attempt to claim the main coordinator role."""
    current_main = check_main()
    if current_main is not None:
        last_hb = get_last_heartbeat(current_main)
        if last_hb and (datetime.now(UTC) - last_hb) < timedelta(minutes=20):
            return ClaimResult(
                False,
                f"Main session held by {current_main}. Last heartbeat: {last_hb.isoformat()}",
            )

    aid = agent_id_str or agent_id()
    sid = session_id_str or session_id()
    write_message(
        {
            "timestamp": now(),
            "session_id": sid,
            "agent_id": aid,
            "branch": "main",
            "type": "main_session_set",
            "topic": "coordination",
            "payload": {},
        }
    )
    return ClaimResult(True, f"Main session claimed by {aid}")


def release_main(agent_id_str: str | None = None) -> None:
    """Release the main coordinator role."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id_str or agent_id(),
            "branch": "main",
            "type": "main_session_released",
            "topic": "coordination",
            "payload": {},
        }
    )


def elect_main() -> ClaimResult:
    """Auto-elect the oldest active session as main."""
    messages = read_messages(limit=500)
    active: dict[str, dict[str, Any]] = {}
    for msg in messages:
        sid = msg.get("session_id")
        if msg.get("type") == "signin":
            active[sid] = msg
        elif msg.get("type") == "signout":
            active.pop(sid, None)
        elif msg.get("type") == "heartbeat":
            active[sid] = msg

    if not active:
        return ClaimResult(False, "No active sessions found")

    oldest = min(active.values(), key=lambda m: m.get("timestamp", ""))
    agent = oldest.get("agent_id", "unknown")
    return claim_main(agent_id_str=agent)


# ---------------------------------------------------------------------------
# High-level helpers (signin, signout, heartbeat, post, send)
# ---------------------------------------------------------------------------


def signin() -> str:
    """Write a signin message."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "signin",
            "topic": "agent-lifecycle",
            "payload": {},
        }
    )
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

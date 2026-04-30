"""FastMCP server for ADHD — the sole interface, no CLI, no scripts."""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from adhd.bus import (
    agent_id,
    archive,
    check_main,
    claim_main,
    current_branch,
    elect_main,
    now,
    read_messages,
    release_main,
    resolve,
    session_id,
    signin,
    signout,
    validate_bus,
    write_message,
)
from adhd.bus import (
    post as bus_post,
)
from adhd.bus import (
    send as bus_send,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

mcp = FastMCP(
    "adhd",
    instructions=(
        "ADHD coordination bus. Use these tools to coordinate with other "
        "agent sessions working on the same repository."
    ),
)

# ---------------------------------------------------------------------------
# Lifecycle tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_signin(role: str = "sub") -> str:
    """Sign in to the ADHD coordination bus. Call once when your session starts.

    Args:
        role: Register as "main" (coordinator) or "sub" (worker, default).
              Only one main can exist at a time. Main claim fails if another
              active main exists. Requires ADHD_ALLOW_MAIN=1.
    """
    if role == "main":
        if not os.environ.get("ADHD_ALLOW_MAIN"):
            return "ERROR: Main claim blocked. Set ADHD_ALLOW_MAIN=1 to claim coordinator role."
        result = claim_main()
        if not result.success:
            return f"ERROR: {result.message}"
        signin_msg = signin()
        return f"Signed in as MAIN. {signin_msg}"
    return signin()


@mcp.tool()
async def adhd_signout() -> str:
    """Sign out from the ADHD coordination bus. Call once before your session ends."""
    return signout()


# ---------------------------------------------------------------------------
# Read / write tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_read(
    limit: int = 50,
    type: str | None = None,
    topic: str | None = None,
    agent: str | None = None,
) -> str:
    """Read recent messages from the ADHD bus.

    Args:
        limit: Maximum number of messages to return (default 50)
        type: Filter by message type (signin, signout, heartbeat, status, etc.)
        topic: Filter by topic (agent-lifecycle, coordination, agent-activity, etc.)
        agent: Filter by agent ID
    """
    messages = read_messages(
        limit=limit,
        type_filter=type,
        topic_filter=topic,
        agent_filter=agent,
    )
    return json.dumps(messages, indent=2)


PROTECTED_TYPES = frozenset(
    {
        "main_session_set",
        "main_session_released",
        "signin",
        "signout",
        "heartbeat",
    }
)


@mcp.tool()
async def adhd_post(type: str, topic: str, payload: str = "{}") -> str:
    """Post a message to the ADHD bus.

    Args:
        type: Message type (status, schema, dependency, event, tool_use)
        topic: Message topic (agent-activity, schema, dependency-graph, etc.)
        payload: JSON string for the payload (must be a JSON object)
    """
    if type in PROTECTED_TYPES:
        return f"ERROR: Message type '{type}' is protected. Use the dedicated tool instead."
    try:
        payload_dict: dict[str, object] = json.loads(payload)
    except json.JSONDecodeError as exc:
        return f"ERROR: Invalid JSON payload: {exc}"
    if not isinstance(payload_dict, dict):
        return "ERROR: payload must be a JSON object"
    return bus_post(type_=type, topic=topic, payload=payload_dict)


@mcp.tool()
async def adhd_send(
    to: str, message: str, topic: str = "agent-request", type: str = "request"
) -> str:
    """Send a request or message to another agent.

    Args:
        to: Target agent ID or "all"
        message: Message body
        topic: Message topic (default: agent-request)
        type: Message type: request, question, or event
    """
    if type in PROTECTED_TYPES:
        return f"ERROR: Message type '{type}' is protected. Use the dedicated tool instead."
    return bus_send(to=to, message=message, topic=topic, type_=type)


# ---------------------------------------------------------------------------
# Main session tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_main_check() -> str:
    """Check who currently holds the main coordinator role."""
    current = check_main()
    if current:
        return f"Main session: {current}"
    return "No main session active"


@mcp.tool()
async def adhd_main_claim() -> str:
    """Claim the main coordinator role.

    Requires ADHD_ALLOW_MAIN=1. Fails if another active main session exists
    (heartbeat within last 20 minutes).
    """
    if not os.environ.get("ADHD_ALLOW_MAIN"):
        return "ERROR: Main claim blocked. Set ADHD_ALLOW_MAIN=1 to claim coordinator role."
    result = claim_main()
    if not result.success:
        return f"ERROR: {result.message}"
    return result.message


@mcp.tool()
async def adhd_main_release() -> str:
    """Release the main coordinator role. Call when your coordinating session ends.

    Only the current main session can release itself.
    """
    current = check_main()
    my_id = agent_id()
    if current is None:
        return "ERROR: No main session is currently active."
    if current != my_id:
        return f"ERROR: You are not the main session. Current main: {current}"
    release_main()
    return "Main session released."


@mcp.tool()
async def adhd_main_elect() -> str:
    """Auto-elect the oldest active session as main coordinator.

    Requires ADHD_ALLOW_MAIN=1.
    """
    if not os.environ.get("ADHD_ALLOW_MAIN"):
        return "ERROR: Main election blocked. Set ADHD_ALLOW_MAIN=1 to elect coordinator role."
    result = elect_main()
    if not result.success:
        return f"ERROR: {result.message}"
    return result.message


# ---------------------------------------------------------------------------
# Maintenance tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_validate() -> str:
    """Validate the ADHD bus file for corrupt or invalid messages."""
    ok, msg = validate_bus()
    if not ok:
        return f"ERROR: {msg}"
    return msg


@mcp.tool()
async def adhd_archive() -> str:
    """Archive old messages when the bus exceeds 10,000 lines."""
    return archive()


@mcp.tool()
async def adhd_resolve() -> str:
    """Print the absolute path to the ADHD bus file for the current repo."""
    return str(resolve())


# ---------------------------------------------------------------------------
# Phase 3: Heartbeat lifecycle (deferred for validation)
# ---------------------------------------------------------------------------

_heartbeat_task: asyncio.Task[None] | None = None


async def heartbeat_loop() -> None:
    """Write a heartbeat every 10 minutes while the session is alive."""
    while True:
        write_message(
            {
                "timestamp": now(),
                "session_id": session_id(),
                "agent_id": agent_id(),
                "branch": current_branch(),
                "type": "heartbeat",
                "topic": "agent-lifecycle",
                "payload": {},
            }
        )
        await asyncio.sleep(600)


@mcp.tool()
async def adhd_start_heartbeat() -> str:
    """Start the background heartbeat timer. Called automatically after signin."""
    global _heartbeat_task
    if _heartbeat_task is not None and not _heartbeat_task.done():
        return "Heartbeat already running."
    _heartbeat_task = asyncio.create_task(heartbeat_loop())
    return "Heartbeat started (every 10 minutes)."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@atexit.register
def _cleanup() -> None:
    """Write signout when the server process exits."""
    try:
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
    except Exception:
        pass


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

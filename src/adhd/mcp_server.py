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
    check_mcp_change_status,
    check_supporters,
    current_branch,
    get_decision_history,
    get_pending_decisions,
    hitl_approve_gonogo,
    hitl_claim_decision,
    hitl_provide_rpe,
    hitl_release_decision,
    hitl_split_duties,
    mark_mcp_change_ready,
    now,
    prepare_mcp_change,
    read_messages,
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
async def adhd_signin() -> str:
    """Sign in to the ADHD coordination bus. Call once when your session starts."""
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
        "signin",
        "signout",
        "heartbeat",
    }
)

PROTECTED_TOPICS = frozenset({"mcp-change"})


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
    if topic in PROTECTED_TOPICS:
        return f"ERROR: Message topic '{topic}' is protected. Use the dedicated tool instead."
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
# Supporter tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_main_check() -> str:
    """Check active supporter sessions on the bus.

    Returns a list of sessions that signed in with supporter=True and have
    a heartbeat within the last 20 minutes.
    """
    supporters = check_supporters()
    if not supporters:
        return "No active supporter sessions."

    lines = [f"Active supporters ({len(supporters)}):"]
    for s in supporters:
        lines.append(f"  {s['agent_id']} (session {s['session_id']}) — last seen {s['timestamp']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP change notification tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_mcp_change_prepare(server: str) -> str:
    """Signal that an MCP server code change is about to start.

    Posts a 'preparing' notification to the bus. Other sessions should
    pause tool calls to this server until the matching 'ready' message.

    Args:
        server: MCP server name (\"adhd\", \"asd\", or \"ocd\")
    """
    return prepare_mcp_change(server)


@mcp.tool()
async def adhd_mcp_change_ready(server: str, commit: str = "") -> str:
    """Signal that an MCP server code change is complete.

    Posts a 'ready' notification to the bus. Other sessions can resume
    tool calls to this server.

    Args:
        server: MCP server name (\"adhd\", \"asd\", or \"ocd\")
        commit: Optional commit hash of the deployed change
    """
    return mark_mcp_change_ready(server, commit)


@mcp.tool()
async def adhd_mcp_change_check() -> str:
    """Check if any MCP server is currently being modified.

    Returns list of servers with a pending 'preparing' notification
    that has no matching 'ready'.
    """
    in_flux = check_mcp_change_status()
    if not in_flux:
        return "No MCP servers are currently being modified."

    lines = ["MCP servers currently in flux:"]
    for s in in_flux:
        lines.append(
            f"  {s['server']} — by {s['agent_id']} "
            f"(session {s['session_id']}) since {s['timestamp']}"
        )
    return "\n".join(lines)


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
# Human-In-The-Loop (HITL) tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_human_claim_decision(
    decision_id: str, description: str, urgency: str = "medium"
) -> str:
    """Claim a pending decision for human review.

    Args:
        decision_id: Unique identifier (e.g., "pr-42-merge")
        description: Human-readable summary of what needs deciding
        urgency: low | medium | high (default medium)
    """
    return hitl_claim_decision(decision_id, description, urgency)


@mcp.tool()
async def adhd_human_release_decision(decision_id: str) -> str:
    """Release a previously claimed decision so another agent can pick it up."""
    return hitl_release_decision(decision_id)


@mcp.tool()
async def adhd_human_provide_rpe(decision_id: str, rpe_value: float, notes: str = "") -> str:
    """Provide Reward Prediction Error feedback for a decision.

    Args:
        decision_id: The decision this RPE applies to
        rpe_value: Numeric RPE (positive = better than expected)
        notes: Optional human-readable context
    """
    return hitl_provide_rpe(decision_id, rpe_value, notes)


@mcp.tool()
async def adhd_human_approve_gonogo(decision_id: str, approved: bool, reason: str = "") -> str:
    """Approve or reject a Go/NoGo action.

    Args:
        decision_id: The action under review
        approved: True to approve, False to reject
        reason: Optional explanation
    """
    return hitl_approve_gonogo(decision_id, approved, reason)


@mcp.tool()
async def adhd_human_split_duties(duties: list[str], target_agents: list[str]) -> str:
    """Split or supplement supporter duties across agents.

    Args:
        duties: List of duty descriptions (e.g., ["bus-monitor", "pr-scan"])
        target_agents: Agent IDs or "all" to broadcast
    """
    return hitl_split_duties(duties, target_agents)


@mcp.tool()
async def adhd_human_pending_decisions() -> str:
    """List all decisions currently claimed but not yet resolved."""
    decisions = get_pending_decisions()
    if not decisions:
        return "No pending decisions."
    return json.dumps(decisions, indent=2)


@mcp.tool()
async def adhd_human_decision_history(decision_id: str) -> str:
    """Return the full message history for a specific decision."""
    history = get_decision_history(decision_id)
    if not history:
        return f"No history found for decision '{decision_id}'."
    return json.dumps(history, indent=2)


# ---------------------------------------------------------------------------
# Phase 3: Heartbeat lifecycle (deferred for validation)
# ---------------------------------------------------------------------------
_heartbeat_task: asyncio.Task[None] | None = None


async def heartbeat_loop() -> None:
    """Write a heartbeat every 10 minutes while the session is alive."""
    while True:
        payload: dict[str, object] = {}
        if os.environ.get("ADHD_ENABLE_SUPPORTER"):
            payload["supporter"] = True

        write_message(
            {
                "timestamp": now(),
                "session_id": session_id(),
                "agent_id": agent_id(),
                "branch": current_branch(),
                "type": "heartbeat",
                "topic": "agent-lifecycle",
                "payload": payload,
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

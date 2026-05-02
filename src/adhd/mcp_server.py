"""FastMCP server for ADHD — the sole interface, no CLI, no scripts."""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from adhd.bus import (
    agent_id,
    announce_migration,
    archive,
    check_mcp_change_status,
    check_noise_threshold,
    check_supporters,
    claim_pr,
    create_snapshot,
    current_branch,
    discover_buses,
    forward_message,
    generate_keypair,
    get_active_claims,
    get_bridge_rules,
    get_bridge_targets,
    get_decision_history,
    get_file_size,
    get_namespace_mappings,
    get_noise_metrics,
    get_pending_decisions,
    get_pending_migration_acks,
    get_perf_level,
    hitl_approve_gonogo,
    hitl_claim_decision,
    hitl_provide_rpe,
    hitl_release_decision,
    hitl_split_duties,
    issue_token,
    mark_mcp_change_ready,
    now,
    prepare_mcp_change,
    read_messages,
    read_messages_since,
    reap_stale_heartbeats,
    register_bridge,
    register_namespace,
    release_pr,
    resolve,
    session_id,
    signin,
    signout,
    subscribe,
    unregister_bridge,
    unregister_namespace,
    validate_bus,
    verify_agent,
    verify_signature,
    verify_token,
    write_message,
)
from adhd.bus import (
    post as bus_post,
)
from adhd.bus import (
    send as bus_send,
)
from adhd.rules import (
    get_rules,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

logger = logging.getLogger(__name__)

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
async def adhd_signout(token: str = "") -> str:
    """Sign out from the ADHD coordination bus. Call once before your session ends.

    Args:
        token: Optional capability token for access control
    """
    err = _check_access(token, "write", "adhd_signout")
    if err:
        return err
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
    recipient: str | None = None,
    token: str = "",
) -> str:
    """Read recent messages from the ADHD bus.

    Args:
        limit: Maximum number of messages to return (default 50)
        type: Filter by message type (signin, signout, heartbeat, status, etc.)
        topic: Filter by topic (agent-lifecycle, coordination, agent-activity, etc.)
        agent: Filter by agent ID
        recipient: Filter by payload.recipient field (use "all" for broadcasts)
        token: Optional capability token for access control
    """
    err = _check_access(token, "read", "adhd_read")
    if err:
        return err
    messages = read_messages(
        limit=limit,
        type_filter=type,
        topic_filter=topic,
        agent_filter=agent,
        recipient_filter=recipient,
    )
    return json.dumps(messages, indent=2)


PROTECTED_TYPES = frozenset(
    {
        "signin",
        "signout",
        "heartbeat",
        "subscription",
        "unsubscription",
        "migration_announce",
        "migration_ack",
        "bridge_rule",
        "namespace_rule",
    }
)

PROTECTED_TOPICS = frozenset({"mcp-change"})

ENFORCE_AC = "ADHD_ENFORCE_ACCESS_CONTROL"


def _check_access(token: str, required_scope: str, required_tool: str) -> str | None:
    """Check token-based access. Returns None if allowed, error JSON if denied."""
    if not token and not os.environ.get(ENFORCE_AC):
        return None
    if not token:
        return json.dumps({"error": "access_denied", "detail": "Token required for access control"})
    caller = agent_id()
    result = verify_token(
        token,
        required_tool=required_tool,
        required_scope=required_scope,
        caller_id=caller,
    )
    if not result["ok"]:
        return json.dumps({"error": "access_denied", "detail": result["detail"]})
    return None


@mcp.tool()
async def adhd_post(type: str, topic: str, payload: str = "{}", token: str = "") -> str:
    """Post a message to the ADHD bus.

    Args:
        type: Message type (status, schema, dependency, event, tool_use)
        topic: Message topic (agent-activity, schema, dependency-graph, etc.)
        payload: JSON string for the payload (must be a JSON object)
        token: Optional capability token for access control
    """
    err = _check_access(token, "write", "adhd_post")
    if err:
        return err
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
    result = bus_post(type_=type, topic=topic, payload=payload_dict)

    msg = {
        "timestamp": now(),
        "session_id": session_id(),
        "agent_id": agent_id(),
        "branch": current_branch(),
        "type": type,
        "topic": topic,
        "payload": payload_dict,
    }
    targets = get_bridge_targets(msg)
    for target in targets:
        forward_message(msg, target)

    if targets:
        result += f" Forwarded to: {', '.join(targets)}."
    return result


@mcp.tool()
async def adhd_send(
    to: str,
    message: str,
    topic: str = "agent-request",
    type: str = "request",
    token: str = "",
) -> str:
    """Send a request or message to another agent.

    Args:
        to: Target agent ID or "all"
        message: Message body
        topic: Message topic (default: agent-request)
        type: Message type: request, question, or event
        token: Optional capability token for access control
    """
    err = _check_access(token, "write", "adhd_send")
    if err:
        return err
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
# Merge-queue tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_merge_claim(pr_number: int) -> str:
    """Claim a PR for merging.

    Other supporters skip claimed PRs. Claims auto-expire after 5 minutes
    to handle crashed agents.

    Args:
        pr_number: The PR number to claim.
    """
    return claim_pr(pr_number)


@mcp.tool()
async def adhd_merge_release(pr_number: int) -> str:
    """Release a previously claimed PR.

    Args:
        pr_number: The PR number to release.
    """
    return release_pr(pr_number)


@mcp.tool()
async def adhd_merge_queue() -> str:
    """Show active PR claims.

    Returns a list of PRs with active claims that are not stale
    (timestamp within the last 5 minutes).
    """
    claims = get_active_claims()
    if not claims:
        return "No active PR claims."

    lines = [f"Active claims ({len(claims)}):"]
    for c in claims:
        lines.append(
            f"  PR #{c['pr']} — claimed by {c['agent_id']} "
            f"(session {c['session_id']}) at {c['timestamp']}"
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
async def adhd_archive(token: str = "") -> str:
    """Archive old messages when the bus exceeds 10,000 lines, or warn at 80% capacity.

    Args:
        token: Optional capability token for access control
    """
    err = _check_access(token, "write", "adhd_archive")
    if err:
        return err
    return archive()


@mcp.tool()
async def adhd_reap_stale() -> str:
    """Auto-signout sessions with heartbeats older than 15 minutes.

    Returns a JSON list of reaped sessions. Keeps the active-supporters
    list accurate when agents crash or exit without signing out.
    """
    reaped = reap_stale_heartbeats()
    if not reaped:
        return "No stale sessions to reap."
    return json.dumps(reaped, indent=2)


@mcp.tool()
async def adhd_resolve() -> str:
    """Print the absolute path to the ADHD bus file for the current repo."""
    return str(resolve())


@mcp.tool()
async def adhd_snapshot() -> str:
    """Create a full-state checkpoint of the bus for recovery and replay.

    Returns message count, timestamp range, registered and active agents,
    subscription state, and bus file path. Read-only diagnostic tool.
    """
    return json.dumps(create_snapshot(), indent=2)


@mcp.tool()
async def adhd_discover() -> str:
    """Scan for active bus channels on this machine.

    Returns metadata for each discovered bus: slug, message count,
    last activity timestamp, file size, and agents seen. Agents can
    call this on startup to find the most populated channel.
    """
    buses = discover_buses()
    return json.dumps(buses, indent=2) if buses else "No bus channels found."


@mcp.tool()
async def adhd_verify_signature(message_json: str) -> str:
    """Verify the HMAC signature on a bus message.

    Args:
        message_json: A single bus message as a JSON string (one line from the bus).

    Returns ok=True if the signature is valid or signing is disabled.
    Returns ok=False with detail if the signature is missing or invalid.
    """
    try:
        msg = json.loads(message_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "detail": f"Invalid JSON: {exc}"})
    if not isinstance(msg, dict):
        return json.dumps({"ok": False, "detail": "Message must be a JSON object"})
    secret = os.environ.get("ADHD_BUS_SECRET")
    if not secret:
        return json.dumps(
            {"ok": True, "detail": "Signing is not enabled (ADHD_BUS_SECRET not set)"}
        )
    if verify_signature(msg):
        return json.dumps({"ok": True, "detail": "Signature valid"})
    return json.dumps({"ok": False, "detail": "Signature invalid — message may have been tampered"})


@mcp.tool()
async def adhd_gen_key(agent_id: str) -> str:
    """Generate an Ed25519 keypair for the given agent.

    Persists PEM-encoded private key and raw-hex public key to
    ``~/.brainxio/adhd/keys/``.  Run once per agent before signin.
    Returns the public-key hex.
    """
    return generate_keypair(agent_id)


@mcp.tool()
async def adhd_verify_agent(agent_id: str, challenge: str, signature: str) -> str:
    """Verify an agent's cryptographic identity.

    Checks that *signature* is a valid Ed25519 signature of *challenge*
    for the given *agent_id*'s public key.  Returns ok=True when the
    identity is confirmed, ok=False when the key is missing or the
    signature doesn't match (impersonation attempt).
    """
    result = verify_agent(agent_id, challenge, signature)
    return json.dumps(
        {
            "ok": result,
            "detail": (
                "Identity verified"
                if result
                else "Verification failed — key missing or signature invalid"
            ),
        }
    )


@mcp.tool()
async def adhd_issue_token(
    issuer_id: str,
    subject: str,
    allowed_tools: str = "[]",
    scopes: str = "[]",
    expiry_hours: int = 24,
) -> str:
    """Issue a signed capability token for *subject* signed by *issuer_id*.

    Tokens allow agents to prove authorization for specific tools and
    scopes.  The issuer must have an Ed25519 keypair (use adhd_gen_key
    first).  Returns a signed token string that can be verified with
    adhd_verify_token and passed to tools like adhd_post and adhd_send.

    Args:
        issuer_id: Agent ID of the token issuer (must have private key)
        subject: Agent ID that will use the token
        allowed_tools: JSON list of tool names the token permits
        scopes: JSON list of scope strings (e.g. '["read", "write"]')
        expiry_hours: Token validity duration in hours (default 24)
    """
    try:
        tools_list: list[str] = json.loads(allowed_tools)
    except json.JSONDecodeError:
        return json.dumps({"ok": False, "detail": "allowed_tools must be valid JSON array"})
    try:
        scopes_list: list[str] = json.loads(scopes)
    except json.JSONDecodeError:
        return json.dumps({"ok": False, "detail": "scopes must be valid JSON array"})

    token = issue_token(
        issuer_id,
        subject,
        allowed_tools=tools_list,
        scopes=scopes_list,
        expiry_hours=expiry_hours,
    )
    if token is None:
        return json.dumps({"ok": False, "detail": f"Issuer '{issuer_id}' has no private key"})
    return json.dumps({"ok": True, "token": token})


@mcp.tool()
async def adhd_verify_token(
    token: str,
    required_tool: str = "",
    caller_id: str = "",
) -> str:
    """Verify a signed capability token.

    Checks token signature, expiry, tool permission, and caller
    identity.  Returns ok=True when all checks pass.

    Args:
        token: The signed token string (from adhd_issue_token)
        required_tool: Optional tool name the token must allow
        caller_id: Optional agent ID that must match the token subject
    """
    result = verify_token(
        token,
        required_tool=required_tool or None,
        caller_id=caller_id or None,
    )
    return json.dumps(result)


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
# Self-describing rules
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_get_rules() -> str:
    """Return structured protocol rules for the ADHD bus.

    Returns a JSON object describing all protocols (heartbeat, supporter,
    mcp-change, merge-queue, HITL), message types, env vars, and tools.
    Agents can call this at startup to learn how the bus works.
    """
    return json.dumps(get_rules(), indent=2)


# ---------------------------------------------------------------------------
# Noise threshold monitoring
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_noise_check() -> str:
    """Return current bus density metrics and check against noise thresholds.

    Reports messages-per-minute, active agent count, and whether configured
    thresholds (ADHD_NOISE_THRESHOLD, ADHD_NOISE_AGENT_THRESHOLD) are exceeded.
    """
    result = check_noise_threshold()
    metrics = get_noise_metrics()
    return json.dumps({"status": result, "metrics": metrics}, indent=2)


# ---------------------------------------------------------------------------
# Push/event-driven delivery tools
# ---------------------------------------------------------------------------

_read_pos: int = 0
_subscribed_filters: dict[str, str] = {}
_explicit_filters: dict[str, str] = {}
_MANDATORY_FILTERS: dict[str, str] = {"recipient": "all"}


def _matches_filters(msg: dict[str, Any], filters: dict[str, str]) -> bool:
    """Check if a message matches the given filter set."""
    payload = msg.get("payload", {})
    for key, value in filters.items():
        if key == "recipient":
            if isinstance(payload, dict):
                if payload.get("recipient") != value:
                    return False
            else:
                return False
        else:
            if msg.get(key) != value:
                return False
    return True


@mcp.tool()
async def adhd_signin() -> str:
    """Sign in to the ADHD coordination bus. Call once when your session starts."""
    global _subscribed_filters, _explicit_filters, _read_pos
    result = signin()
    _explicit_filters = {}
    _subscribed_filters = dict(_MANDATORY_FILTERS)
    _read_pos = 0
    subscribe(_MANDATORY_FILTERS)
    return result


@mcp.tool()
async def adhd_subscribe(
    type: str | None = None,
    topic: str | None = None,
    recipient: str | None = None,
    token: str = "",
) -> str:
    """Subscribe to bus messages matching given filters.

    Registers a subscription on the bus so other agents know what you're
    interested in. Also caches filters locally for adhd_poll/adhd_wait.

    Args:
        type: Only match messages of this type
        topic: Only match messages of this topic
        recipient: Only match messages with this payload.recipient
        token: Optional capability token for access control
    """
    err = _check_access(token, "read", "adhd_subscribe")
    if err:
        return err
    global _subscribed_filters, _explicit_filters
    filters: dict[str, str] = {}
    if type:
        filters["type"] = type
    if topic:
        filters["topic"] = topic
    if recipient:
        filters["recipient"] = recipient
    if not filters:
        return "ERROR: At least one filter (type, topic, recipient) is required."
    _explicit_filters = filters
    merged = {**_explicit_filters, **_MANDATORY_FILTERS}
    _subscribed_filters = merged
    return subscribe(merged)


@mcp.tool()
async def adhd_unsubscribe() -> str:
    """Remove the current agent's explicit subscription, but keep mandatory 'all'."""
    global _subscribed_filters, _explicit_filters
    _explicit_filters = {}
    _subscribed_filters = dict(_MANDATORY_FILTERS)
    subscribe(_MANDATORY_FILTERS)
    return "Unsubscribed."


@mcp.tool()
async def adhd_poll(token: str = "") -> str:
    """Return new unread bus messages matching active subscriptions.

    Returns only messages posted since the last adhd_poll or adhd_wait call.
    Does not block — returns empty if nothing new.

    Args:
        token: Optional capability token for access control
    """
    err = _check_access(token, "read", "adhd_poll")
    if err:
        return err
    global _read_pos
    msgs, new_pos = read_messages_since(_read_pos)
    _read_pos = new_pos
    matching = [
        msg
        for msg in msgs
        if (_explicit_filters and _matches_filters(msg, _explicit_filters))
        or _matches_filters(msg, _MANDATORY_FILTERS)
    ]
    if not matching:
        return "[]"
    return json.dumps(matching, indent=2)


@mcp.tool()
async def adhd_wait(timeout: float = 30.0) -> str:
    """Block until a matching message arrives or timeout expires.

    Watches the bus file for changes and returns as soon as a message
    matching the active subscription appears. Returns empty list on timeout.

    Args:
        timeout: Maximum seconds to wait (default 30, max 120)
    """
    global _read_pos
    timeout = min(timeout, 120.0)
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        current_size = get_file_size()
        if current_size > _read_pos:
            msgs, new_pos = read_messages_since(_read_pos)
            _read_pos = new_pos
            matching = [
                msg
                for msg in msgs
                if (_explicit_filters and _matches_filters(msg, _explicit_filters))
                or _matches_filters(msg, _MANDATORY_FILTERS)
            ]
            if matching:
                return json.dumps(matching, indent=2)
            # File grew but no matching messages — update position and keep waiting
            _read_pos = current_size

        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return "[]"
        await asyncio.sleep(min(0.5, remaining))


@mcp.tool()
async def adhd_migrate_to_push() -> str:
    """Broadcast migration to push/event-driven delivery.

    Posts migration announcements repeatedly until all active agents
    acknowledge they've switched to push and ditched their monitors.
    Runs for up to 10 announcement cycles.
    """
    max_cycles = 10
    for cycle in range(1, max_cycles + 1):
        announce_migration()
        await asyncio.sleep(5)

        supporters = check_supporters()
        active_agents = [s["agent_id"] for s in supporters]
        active_agents.append(agent_id())

        pending = get_pending_migration_acks(active_agents)
        if not pending:
            return (
                f"All {len(active_agents)} active agents acknowledged migration in cycle {cycle}."
            )
        logger.info("Migration cycle %d: %d agents still pending: %s", cycle, len(pending), pending)

    # Final check
    supporters = check_supporters()
    active_agents = [s["agent_id"] for s in supporters]
    active_agents.append(agent_id())
    pending = get_pending_migration_acks(active_agents)
    if pending:
        return (
            f"Migration incomplete after {max_cycles} cycles. "
            f"Still pending: {pending}. Will retry on next call."
        )
    return f"All {len(active_agents)} agents acknowledged migration."


# ---------------------------------------------------------------------------
# Cross-bus bridging tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_bridge_register(
    target_slug: str,
    type: str | None = None,
    topic: str | None = None,
) -> str:
    """Register a bridge that forwards matching messages to another bus.

    Creates a bridge rule on the bus. When messages are posted via adhd_post
    and match the optional type/topic filters, they are automatically forwarded
    to the target bus. If no filters are given, all messages are forwarded.

    Args:
        target_slug: The slug name of the target bus (e.g., "v0.1.0-alpha")
        type: Only forward messages of this type (optional)
        topic: Only forward messages of this topic (optional)
    """
    return register_bridge(target_slug, type_filter=type, topic_filter=topic)


@mcp.tool()
async def adhd_bridge_unregister(target_slug: str) -> str:
    """Remove a bridge rule so messages stop forwarding to the target bus.

    Args:
        target_slug: The slug name of the target bus to stop forwarding to
    """
    return unregister_bridge(target_slug)


@mcp.tool()
async def adhd_bridge_list() -> str:
    """List all active bridge rules.

    Returns each bridge's source, target, filters, and registration metadata.
    """
    rules = get_bridge_rules()
    if not rules:
        return "No active bridge rules."
    return json.dumps(rules, indent=2)


# ---------------------------------------------------------------------------
# Namespace routing tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def adhd_namespace_register(namespace: str, target_slug: str) -> str:
    """Register a namespace that resolves to a specific bus slug.

    Agents can send messages to agent@namespace and they will be
    forwarded to the bus associated with the namespace.

    Args:
        namespace: The namespace name (e.g., "my-project")
        target_slug: The bus slug to route messages to
    """
    return register_namespace(namespace, target_slug)


@mcp.tool()
async def adhd_namespace_unregister(namespace: str) -> str:
    """Remove a namespace routing rule.

    Args:
        namespace: The namespace to remove
    """
    return unregister_namespace(namespace)


@mcp.tool()
async def adhd_namespace_list() -> str:
    """List all registered namespace routing rules.

    Returns each namespace, its target bus slug, and registration metadata.
    """
    mappings = get_namespace_mappings()
    if not mappings:
        return "No namespace routing rules."
    return json.dumps(mappings, indent=2)


# ---------------------------------------------------------------------------
# Phase 3: Heartbeat lifecycle
# ---------------------------------------------------------------------------
_heartbeat_task: asyncio.Task[None] | None = None


async def heartbeat_loop() -> None:
    """Write a heartbeat every 10 minutes while the session is alive."""
    while True:
        payload: dict[str, object] = {}
        if os.environ.get("ADHD_ENABLE_SUPPORTER"):
            payload["supporter"] = True
            payload["perf_level"] = get_perf_level()

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

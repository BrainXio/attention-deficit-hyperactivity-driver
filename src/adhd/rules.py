"""Self-describing protocol rules for the ADHD bus.

This module exposes the current bus protocol rules so agents can discover
how to work with the bus at runtime — no external docs required.
"""

from __future__ import annotations


def get_rules() -> dict[str, object]:
    """Return structured protocol rules for the ADHD bus.

    Versioned and matching the current bus schema. MCP clients can
    call adhd_get_rules at startup to learn the coordination protocol.
    """
    return {
        "package": "adhd",
        "version": "0.1.0",
        "protocols": {
            "signin_signout": {
                "description": "Every session must sign in on start and sign out before exit",
                "signin_tool": "adhd_signin",
                "signout_tool": "adhd_signout",
                "signout_on_exit": "Automatic via atexit handler",
            },
            "heartbeat": {
                "description": "Periodic alive signal written by each session",
                "interval_minutes": 10,
                "timeout_minutes": 20,
                "tool": "adhd_start_heartbeat",
                "note": "Heartbeat starts automatically after signin via MCP prompt",
            },
            "supporter": {
                "description": "Additive helper sessions that monitor CI, archive, and nudge",
                "model": "additive",
                "env_var": "ADHD_ENABLE_SUPPORTER",
                "env_value": "1",
                "note": "Multiple supporters can coexist safely — no exclusive locks",
                "perf_level": {
                    "env_var": "ADHD_PERF_LEVEL",
                    "values": ["low", "medium", "high"],
                    "default": "medium",
                },
            },
            "mcp_change": {
                "description": "Coordination for MCP server code changes across sessions",
                "prepare_tool": "adhd_mcp_change_prepare",
                "ready_tool": "adhd_mcp_change_ready",
                "check_tool": "adhd_mcp_change_check",
                "prepare_wait_seconds": 5,
                "note": "Pause tool calls to a server when 'preparing' appears, resume on 'ready'",
            },
            "merge_queue": {
                "description": "Explicit PR claim protocol for merge coordination",
                "claim_tool": "adhd_merge_claim",
                "release_tool": "adhd_merge_release",
                "queue_tool": "adhd_merge_queue",
                "claim_ttl_minutes": 5,
                "note": "Stale claims (>5 min) are automatically invalidated",
            },
            "hitl": {
                "description": "Human-In-The-Loop intervention in agent decisions",
                "tools": [
                    "adhd_human_claim_decision",
                    "adhd_human_provide_rpe",
                    "adhd_human_approve_gonogo",
                    "adhd_human_split_duties",
                ],
                "note": "State lives on the bus — another-intelligence reads and reacts",
            },
            "rules": {
                "description": "Self-describing bus protocol (this tool)",
                "tool": "adhd_get_rules",
            },
        },
        "message_types": [
            {"type": "signin", "topic": "agent-lifecycle", "description": "Session started"},
            {"type": "signout", "topic": "agent-lifecycle", "description": "Session ended"},
            {"type": "heartbeat", "topic": "agent-lifecycle", "description": "Liveness signal"},
            {"type": "status", "topic": "agent-activity", "description": "Progress update"},
            {"type": "schema", "topic": "schema", "description": "Shared API schema"},
            {"type": "dependency", "topic": "dependency-graph", "description": "Declare deps"},
            {"type": "question", "topic": "*", "description": "Blocking question"},
            {"type": "answer", "topic": "*", "description": "Response to question"},
            {"type": "event", "topic": "*", "description": "General event"},
            {"type": "tool_use", "topic": "agent-activity", "description": "Tool used"},
            {"type": "request", "topic": "agent-request", "description": "Ask for help"},
            {"type": "response", "topic": "agent-request", "description": "Reply"},
            {"type": "hitl_claim", "topic": "hitl-decisions", "description": "Claim decision"},
            {"type": "hitl_release", "topic": "hitl-decisions", "description": "Release decision"},
            {"type": "hitl_rpe", "topic": "hitl-decisions", "description": "Provide RPE feedback"},
            {"type": "hitl_approve", "topic": "hitl-decisions", "description": "Approve/reject"},
            {"type": "hitl_split", "topic": "hitl-decisions", "description": "Split duties"},
        ],
        "env_vars": [
            {
                "name": "ADHD_BUS_PATH",
                "purpose": "Storage directory prefix",
                "default": "~/.brainxio/adhd",
            },
            {
                "name": "ADHD_BUS_SLUG",
                "purpose": "Bus name/key in the storage directory",
                "default": "git toplevel directory name (parent repo if submodule)",
            },
            {
                "name": "ADHD_SESSION_ID",
                "purpose": "Fixed session identifier",
                "default": "random 8-char UUID",
            },
            {
                "name": "ADHD_AGENT_ID",
                "purpose": "Agent identifier",
                "default": "agent-{session_id}",
            },
            {
                "name": "ADHD_ENABLE_SUPPORTER",
                "purpose": "Mark session as a supporter (additive)",
                "valid_values": ["1"],
            },
            {
                "name": "ADHD_PERF_LEVEL",
                "purpose": "Supporter capability level",
                "valid_values": ["low", "medium", "high"],
                "default": "medium",
            },
        ],
        "tools": [
            {"tool": "adhd_signin", "purpose": "Register session on the bus"},
            {"tool": "adhd_signout", "purpose": "Deregister session"},
            {"tool": "adhd_start_heartbeat", "purpose": "Start background heartbeat"},
            {"tool": "adhd_read", "purpose": "Read/filter bus messages"},
            {"tool": "adhd_post", "purpose": "Post a generic message"},
            {"tool": "adhd_send", "purpose": "Send message to specific agent"},
            {"tool": "adhd_main_check", "purpose": "Check active supporter sessions"},
            {"tool": "adhd_validate", "purpose": "Validate bus integrity"},
            {"tool": "adhd_archive", "purpose": "Archive old messages"},
            {"tool": "adhd_resolve", "purpose": "Print canonical bus path"},
            {"tool": "adhd_mcp_change_prepare", "purpose": "Signal server change starting"},
            {"tool": "adhd_mcp_change_ready", "purpose": "Signal server change complete"},
            {"tool": "adhd_mcp_change_check", "purpose": "Check for changes in progress"},
            {"tool": "adhd_merge_claim", "purpose": "Claim a PR for merging"},
            {"tool": "adhd_merge_release", "purpose": "Release a claimed PR"},
            {"tool": "adhd_merge_queue", "purpose": "Show active PR claims"},
            {"tool": "adhd_human_claim_decision", "purpose": "Human claims a pending decision"},
            {"tool": "adhd_human_provide_rpe", "purpose": "Human provides RPE feedback"},
            {"tool": "adhd_human_approve_gonogo", "purpose": "Approve/reject Go/NoGo action"},
            {"tool": "adhd_human_split_duties", "purpose": "Human splits supporter duties"},
            {"tool": "adhd_gen_key", "purpose": "Generate Ed25519 keypair for an agent"},
            {"tool": "adhd_verify_agent", "purpose": "Verify an agent's cryptographic identity"},
            {"tool": "adhd_get_rules", "purpose": "Return these protocol rules"},
        ],
    }

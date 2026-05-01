# ADHD Architecture

## Overview

ADHD (Attention Deficit Hyperactivity Driver) is a framework-agnostic coordination layer for multiple AI agent sessions. It provides a shared message bus that all sessions can read and write to, enabling awareness and collaboration between parallel work. It works with Claude Code, Cursor, Another Intelligence, or any agent with MCP support.

## Design Principles

### 1. Append-Only JSONL

The bus is a simple append-only file of JSON lines. This is the same format used by `git reflog` and `jq -c`. It is:

- **Human-readable**: `cat ~/.brainxio/adhd/{repo}/bus.jsonl | jq .`
- **Machine-parseable**: `while read line; do echo $line | jq .type; done`
- **Resilient**: Corrupt lines are skipped, not fatal
- **Simple**: No server, no database, no network

### 2. Centralized Bus Path

The bus lives at `~/.brainxio/adhd/{name}/bus.jsonl`. This centralizes coordination state outside any single repo, enabling cross-repo sessions to share a bus. The name is derived from the git toplevel directory name, overridable via `ADHD_BUS_NAME`.

### 3. Supporter Sessions

Supporter sessions are opted in via `ADHD_ENABLE_SUPPORTER=1`. They monitor CI, archive the bus, and nudge stale agents. Unlike the old coordinator model:

- Multiple supporters can coexist safely
- No claim/release lifecycle — supporters are additive
- If a supporter crashes, others continue uninterrupted

### 4. Heartbeat Protocol

Every agent writes a heartbeat every 10 minutes. If an agent misses 2 heartbeats (20 min), it is considered inactive. Supporter sessions can:

- Detect silent agents and post nudges to the bus
- Archive the bus when it grows too large
- Monitor CI pipelines and post results

## Components

```
repo-root/
  src/adhd/
    __init__.py         # Package marker
    bus.py              # Core logic (resolve, I/O, validation, archival)
    models.py           # Pydantic models
    mcp_server.py       # FastMCP server
    notifications.py    # Desktop and Telegram notification helpers
    rules.py            # Protocol rules for self-describing bus
  scripts/
    detect-perf-level.py # Hardware probe for perf_level suggestion
    hitl-notify.py       # HITL decision polling daemon
  .mcp.json             # MCP server registration
  .gitignore
  ~/.brainxio/adhd/
    {repo-slug}/
      bus.jsonl          # The bus (outside any repo)
      bus_archive_*.jsonl # Old messages
```

## Environment Variables

| Variable                | Purpose                                                              |
| ----------------------- | -------------------------------------------------------------------- |
| `ADHD_BUS_PATH`         | Storage directory prefix (default: `~/.brainxio/adhd`)               |
| `ADHD_BUS_SLUG`         | Bus name/key in that directory (default: git toplevel name)          |
| `ADHD_SESSION_ID`       | Fixed session identifier (default: random 8-char UUID)               |
| `ADHD_AGENT_ID`         | Agent identifier (default: `agent-{session_id}`)                     |
| `ADHD_PERF_LEVEL`       | Supporter capability: `low`, `medium`, or `high` (default: `medium`) |
| `ADHD_ENABLE_SUPPORTER` | Set to `1` to mark session as a supporter (additive)                 |
| `ADHD_NOTIFY_URGENCY`   | notify-send urgency level: `low`, `normal`, `critical`               |
| `ADHD_NOTIFY_INTERVAL`  | Polling interval in seconds for `hitl-notify.py --daemon`            |
| `TELEGRAM_BOT_TOKEN`    | Telegram bot token for notification fallback                         |
| `TELEGRAM_CHAT_ID`      | Telegram chat ID for notification fallback                           |

### Cross-Repo Coordination

To join another repo's bus from any session:

```bash
ADHD_BUS_SLUG=projects uv run adhd-mcp
```

This is useful when `ai-o4a/` agents need to coordinate with the master `projects` bus.

## MCP Server

The sole interface is `adhd-mcp`, a FastMCP stdio server. All agent interactions go through MCP tools with JSON schema validation, auto-discovery, and server-managed lifecycle.

### Tools

| Tool                           | Purpose                                   |
| ------------------------------ | ----------------------------------------- |
| `adhd_signin`                  | Register session on the bus               |
| `adhd_signout`                 | Deregister session                        |
| `adhd_start_heartbeat`         | Start background heartbeat timer          |
| `adhd_read`                    | Read/filter messages                      |
| `adhd_post`                    | Post a generic message                    |
| `adhd_send`                    | Send message to specific agent            |
| `adhd_main_check`              | Check active supporter sessions           |
| `adhd_validate`                | Validate bus integrity                    |
| `adhd_archive`                 | Archive old messages and reap stale       |
| `adhd_reap_stale`              | Auto-signout sessions with old heartbeats |
| `adhd_resolve`                 | Print canonical bus path                  |
| `adhd_get_rules`               | Return structured protocol rules          |
| `adhd_mcp_change_prepare`      | Signal server code change about to start  |
| `adhd_mcp_change_ready`        | Signal server code change complete        |
| `adhd_mcp_change_check`        | Check if any server is being modified     |
| `adhd_human_claim_decision`    | Claim a HITL decision for human review    |
| `adhd_human_release_decision`  | Release a claimed HITL decision           |
| `adhd_human_provide_rpe`       | Provide RPE feedback for a decision       |
| `adhd_human_approve_gonogo`    | Approve or reject a Go/NoGo action        |
| `adhd_human_split_duties`      | Split supporter duties across agents      |
| `adhd_human_pending_decisions` | List all pending HITL decisions           |
| `adhd_human_decision_history`  | Get history for a specific decision       |

## Message Flow

```
  Agent A         Agent B         Supporter
       |               |               |
       |-- signin----->|               |
       |               |-- signin----->|
       |               |               |-- adhd_main_check
       |-- heartbeat-->|               |
       |               |-- heartbeat-->|
       |               |               |-- heartbeat
       |               |               |
       |-- request---->|               |
       |               |-- response--->|
       |               |               |
       |-- status----->|               |
       |               |               |-- adhd_read
       |               |               |
       |-- signout---->|               |
       |               |-- signout---->|
```

## Error Handling

- **Bus file missing**: Created on first write
- **Invalid JSON**: Skipped by readers, flagged by validators
- **Missing required field**: Skipped by readers
- **Corrupt archive**: Archived file is skipped, bus continues
- **Disk full**: Writes fail, agents fall back to solo mode

## MCP Change Notification Protocol

When an agent modifies MCP server code in adhd, asd, or ocd, it must notify other sessions to prevent transient tool errors during hot-reload deployments.

### Protocol

1. **Before change**: Call `adhd_mcp_change_prepare(server="<name>")`
2. **Wait ~5 seconds** for other sessions to see the notification and pause tool calls
3. **After change**: Call `adhd_mcp_change_ready(server="<name>", commit="<hash>")`
4. **For other sessions**: When seeing a "preparing" notification (via `adhd_mcp_change_check`), pause MCP tool calls to that server until the matching "ready" appears

### Bus Message Format

```json
{
  "type": "event",
  "topic": "mcp-change",
  "payload": {
    "server": "asd",
    "action": "preparing",
    "branch": "feat/xyz",
    "session_id": "a1b2c3d4"
  }
}
```

For "ready":

```json
{
  "type": "event",
  "topic": "mcp-change",
  "payload": {
    "server": "asd",
    "action": "ready",
    "commit": "abc123def",
    "session_id": "a1b2c3d4"
  }
}
```

The `adhd_mcp_change_check` tool scans the bus for servers that have a "preparing" without a matching "ready". If an agent crashes between prepare and ready, the server appears in-flux until the session's heartbeat expires naturally (20 min).

## Merge-Queue Protocol

Supporters coordinate PR merges through a claim/release protocol on the bus to avoid race conditions.

### Protocol

1. **Claim**: Supporters call `claim_pr(pr_number)` before reviewing a PR
2. **Review and merge**: Only the claiming supporter acts on the PR
3. **Release**: After merge or abandonment, call `release_pr(pr_number)`
4. **Auto-expiry**: Claims auto-expire after 5 minutes to handle crashed agents
5. **Stale detection**: Other supporters check active claims via `get_active_claims()` before processing

### Bus Message Format

```json
{
  "type": "event",
  "topic": "merge-queue",
  "payload": {
    "pr": 42,
    "action": "claim",
    "session_id": "a1b2c3d4"
  }
}
```

## Human-In-The-Loop (HITL) Protocol

When agents reach decisions requiring human judgment (PR approvals, risky deployments, duty reassignment), they post HITL messages to the bus. Humans or supporter agents review and resolve these decisions.

### Decision Lifecycle

1. **Claim**: Agent posts `hitl_claim` with decision_id, description, and urgency (low/medium/high)
2. **Review**: Human claims the decision via `adhd_human_claim_decision`
3. **Resolve**: Human approves/rejects (Go/NoGo) or provides RPE feedback
4. **Release**: Unclaimed decisions can be released for another reviewer

### Message Types

| Type           | Purpose                                 |
| -------------- | --------------------------------------- |
| `hitl_claim`   | Register a new decision for review      |
| `hitl_release` | Release a claim without resolving       |
| `hitl_rpe`     | Record reward prediction error feedback |
| `hitl_approve` | Approve or reject a Go/NoGo action      |
| `hitl_split`   | Split or reassign supporter duties      |

Decisions auto-expire after 30 minutes. Pending decisions are queried via `adhd_human_pending_decisions`.

## Notification System

When HITL decisions require human attention, the notification system delivers alerts through the best available channel.

### Channels

- **notify-send** (primary): Linux desktop notifications via D-Bus. Urgency configurable via `ADHD_NOTIFY_URGENCY`.
- **Telegram Bot API** (fallback): If `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set, falls back to push notifications.
- **Graceful degradation**: If neither channel is available, logs a warning and continues.

### Polling Daemon

`scripts/hitl-notify.py` polls the bus for new pending decisions and sends notifications. In `--daemon` mode it runs continuously with a configurable interval (`ADHD_NOTIFY_INTERVAL`, default 30s). Already-notified decisions are tracked in `.hitl_notified_ids` to avoid duplicate alerts.

## Perf Level Detection

`scripts/detect-perf-level.py` is a standalone hardware probe that suggests an `ADHD_PERF_LEVEL` value. It is not imported by `adhd-mcp` — agents run it once to configure their environment.

### Detection Logic

- **high**: GPU with >= 8GB VRAM, >= 8 CPU cores, >= 16GB RAM
- **medium**: GPU with >= 4GB VRAM, or >= 4 CPU cores and >= 8GB RAM
- **low**: everything else

If `ADHD_PERF_LEVEL` is already set in the environment, the script prints the current value and exits without probing.

## Stale Heartbeat Reaper

`reap_stale_heartbeats()` auto-signs out sessions whose most recent heartbeat or signin is older than 15 minutes. This prevents crashed or exited agents from appearing active indefinitely.

The reaper runs automatically during `adhd_archive` and can also be triggered manually via `adhd_reap_stale`. Each reaped session gets a signout message with reason `"stale-heartbeat-reaped"`, ensuring subsequent heartbeats from a restarted agent are not confused with the old session.

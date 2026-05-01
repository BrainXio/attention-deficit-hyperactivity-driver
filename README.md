# ADHD — Attention Deficit Hyperactivity Driver

> **Attention Deficit Hyperactivity Driver** (ADHD) is the executive function layer for multi-agent AI workflows.
>
> It coordinates multiple parallel agent sessions that would otherwise operate in isolation — adding the missing conductor that keeps parallel processes from colliding.

## The ADHD Parallel

ADHD isn't a deficit of attention — it's a deficit of *coordination*. The brain has plenty of parallel processes (ideas, impulses, observations) but lacks a reliable conductor to sequence them, prioritize them, and keep them from colliding.

Sound familiar? That's exactly what happens when you spawn 5 Claude Code worktrees and let them run loose:

- **Hyperfocus**: One agent rewrites the API while another is still documenting the old one
- **Impulsivity**: Agents push PRs without checking if dependencies are merged
- **Working memory overload**: No one remembers what the other 4 agents decided 20 minutes ago
- **Time blindness**: An agent goes silent for hours — crashed? Blocked? Finished?

This project is the *medication* for multi-agent chaos. Not by suppressing the parallelism (that's the superpower), but by adding the missing executive functions.

## Superpowers

ADHD externalizes the executive function superpowers that multi-agent systems desperately need:

- **Signin/Signout**: "I exist, I'm working on X" — agents announce their presence and intent
- **Heartbeat**: "Still alive, not blocked, last did Y" — continuous liveness monitoring prevents silent crashes
- **Supporter Sessions**: Optional helper sessions that monitor CI, archive the bus, and nudge stale agents. Multiple supporters can coexist safely without exclusive locks.
- **Request/Response**: "Can someone review my PR?" → "On it" — targeted messaging between agents
- **Archival**: Don't let the log grow unbounded (the ADHD notebook problem) — automatic archival keeps the bus responsive

## Quick Start

```bash
# Clone and install
git clone https://github.com/brainxio/attention-deficit-hyperactivity-driver
uv pip install -e .

# Start the MCP server
uv run adhd-mcp
```

The `.mcp.json` in the repo root auto-starts the MCP server when Claude Code opens the project.

### Cross-Repo Coordination

Set `ADHD_BUS_SLUG=projects` to join the master coordination bus:

```bash
ADHD_BUS_SLUG=projects uv run adhd-mcp
```

## Architecture

### Message Schema

The bus is an append-only JSONL file stored at `~/.brainxio/adhd/{repo-slug}/bus.jsonl`. Every line is a JSON object:

```json
{
  "timestamp": "2026-04-29T12:00:00Z",
  "session_id": "a1b2c3d4",
  "agent_id": "feat/docker-image",
  "branch": "feat/docker-image",
  "type": "heartbeat",
  "topic": "agent-lifecycle",
  "payload": {}
}
```

Types: `signin`, `signout`, `heartbeat`, `status`, `schema`, `dependency`, `question`, `answer`, `event`, `tool_use`, `request`, `response`, `hitl_claim`, `hitl_release`, `hitl_rpe`, `hitl_approve`, `hitl_split`

### Bus Path Convention

The bus lives at `~/.brainxio/adhd/{repo-slug}/bus.jsonl`, centralizing coordination state outside any single repo and enabling cross-repo sessions to share a bus.

### Design Philosophy

- **Simple over smart.** Append-only JSONL. No server, no database, no network.
- **Explicit over automatic.** Supporter sessions opt in via `ADHD_ENABLE_SUPPORTER=1`. No exclusive locks.
- **Graceful degradation.** Missing bus? Agents continue working solo.

## MCP Integration

The sole interface is `adhd-mcp`, a FastMCP stdio server. It works with Claude Code, Cursor, Another Intelligence, or any agent with MCP support.

| Tool                           | Purpose                         | ADHD Parallel                               |
| ------------------------------ | ------------------------------- | ------------------------------------------- |
| `adhd_resolve`                 | Find canonical bus path         | Knowing where you left your keys            |
| `adhd_validate`                | Validate JSONL schema           | Checking your work before submitting        |
| `adhd_signin`                  | Write signin message            | "I'm here, I'm going to do X"               |
| `adhd_signout`                 | Write signout message           | "I'm done, here's what happened"            |
| `adhd_start_heartbeat`         | Background heartbeat            | "Still alive, not blocked, making progress" |
| `adhd_post`                    | Post generic message            | Sharing a thought with the group            |
| `adhd_read`                    | Read/filter messages            | Catching up on what you missed              |
| `adhd_send`                    | Send request to specific agent  | "Hey, can you help me with...?"             |
| `adhd_archive`                 | Archive old messages + reap     | Cleaning up your workspace                  |
| `adhd_reap_stale`              | Reap stale heartbeats           | Removing agents that crashed silently       |
| `adhd_main_check`              | Check active supporter sessions | Who's monitoring the room                   |
| `adhd_mcp_change_prepare`      | Signal server change starting   | Announcing you're about to modify code      |
| `adhd_mcp_change_ready`        | Signal server change complete   | Letting others know the server is back      |
| `adhd_mcp_change_check`        | Check for changes in progress   | Checking if any server is being modified    |
| `adhd_get_rules`               | Return protocol rules           | Learning how the bus works                  |
| `adhd_human_claim_decision`    | Claim HITL decision for review  | Asking for a decision                       |
| `adhd_human_release_decision`  | Release claimed HITL decision   | Handing off a decision to someone else      |
| `adhd_human_provide_rpe`       | Provide RPE feedback            | Learning from past decisions                |
| `adhd_human_approve_gonogo`    | Approve/reject Go/NoGo action   | Making the call                             |
| `adhd_human_split_duties`      | Split supporter duties          | Delegating tasks                            |
| `adhd_human_pending_decisions` | List pending HITL decisions     | What still needs attention                  |
| `adhd_human_decision_history`  | Get decision history            | Reviewing how a decision was made           |

### Cross-Repo Integration

ADHD is consumed as an MCP server by all other BrainXio packages:

- **Another-Intelligence**: Discovers ADHD at runtime via MCP registry; routes coordination calls through it
- **OCD**: Uses ADHD bus for PR announcements and review requests
- **ASD**: Posts KB status updates to the bus for cross-agent awareness

## Persistent Memory & RPE

The bus *is* the persistence layer. Every signin, heartbeat, decision, and message is permanently recorded in the append-only JSONL. This gives agents:

- **Full session history**: Replay the entire coordination state of any past session
- **Crash recovery**: New sessions can read the bus to reconstruct context from crashed agents
- **Performance tracking**: Heartbeat payloads carry perf_level data for supporter capability routing

## Scripts

| Script                         | Purpose                                    |
| ------------------------------ | ------------------------------------------ |
| `scripts/detect-perf-level.py` | Probe hardware and suggest ADHD_PERF_LEVEL |
| `scripts/hitl-notify.py`       | Poll bus for HITL decisions and notify     |

Run scripts from the repo root. They are standalone and not imported by `adhd-mcp`.

## Development & Contribution

```bash
# Setup
uv sync
uv pip install -e ".[dev]"

# Tests
uv run pytest -q
uv run pytest -q tests/test_bus.py

# Lint & format
uv run ruff check .
uv run ruff format --check .

# Type check
uv run mypy src/adhd/
```

**Contribution guidelines**: See `CONTRIBUTING.md` for branch naming, conventional commits, PR workflow, and code style. All development must happen in worktrees.

## Related Repos & Roadmap

### Ecosystem

| Package                  | Directory                      | Role                                     | Type         |
| ------------------------ | ------------------------------ | ---------------------------------------- | ------------ |
| **Another-Intelligence** | `another-intelligence/`        | Cognitive core — PPAC loop               | Agent / Host |
| **ASD**                  | `autism-spectrum-driver/`      | Systematizing memory — KB compilation    | MCP Server   |
| **OCD**                  | `obsessive-compulsive-driver/` | Discipline & enforcement — quality gates | MCP Server   |

### Roadmap

- [x] Append-only JSONL bus with signin/signout/heartbeat/post/read/send
- [x] MCP server with 22 tools including HITL, supporter, reaper, notifications
- [x] Supporter model with opt-in sessions and perf_level routing
- [x] MCP change notification protocol (preparing/ready)
- [x] Merge-queue claim protocol with auto-expiry
- [x] Human-In-The-Loop decision system with RPE feedback
- [x] Notification system (desktop + Telegram) for HITL alerts
- [x] Hardware probe for perf_level detection
- [x] Stale heartbeat reaper for accurate supporter list
- [ ] Recipient filter on adhd_read for targeted message retrieval
- [ ] Agent-noise-threshold monitoring for bus density warnings

## License

Apache-2.0. See `LICENSE`.

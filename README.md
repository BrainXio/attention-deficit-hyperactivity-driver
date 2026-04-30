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

This project is the *medication* for multi-agent chaos. Not by suppressing the parallelism (that's the superpower), but by adding the missing executive functions:

- **Signin/Signout**: "I exist, I'm working on X"
- **Heartbeat**: "Still alive, not blocked, last did Y"
- **Supporter Sessions**: Optional helper sessions that monitor CI, archive the bus, and nudge stale agents. Multiple supporters can coexist safely.
- **Request/Response**: "Can someone review my PR?" → "On it"
- **Archival**: Don't let the log grow unbounded (the ADHD notebook problem)

## What This Is

An MCP-native JSONL-based message bus for coordinating multiple AI agent sessions working on the same repository. It works with Claude Code, Cursor, Another Intelligence, or any agent with MCP support. Think of it as a shared whiteboard that all agents can read and write to.

## Core Architecture

### Message Schema

Every line is a JSON object:

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

Types: `signin`, `signout`, `heartbeat`, `status`, `schema`, `dependency`, `question`, `answer`, `event`, `tool_use`, `request`, `response`

### MCP Server

The sole interface is `adhd-mcp`, a FastMCP stdio server registered via `.mcp.json`.

| Tool                   | Purpose                          | ADHD Parallel                                      |
| ---------------------- | -------------------------------- | -------------------------------------------------- |
| `adhd_resolve`         | Find canonical bus path          | Knowing where you left your keys                   |
| `adhd_validate`        | Validate JSONL schema            | Checking your work before submitting               |
| `adhd_signin`          | Write signin message             | "I'm here, I'm going to do X"                      |
| `adhd_signout`         | Write signout message            | "I'm done, here's what happened"                   |
| `adhd_start_heartbeat` | Background heartbeat             | "Still alive, not blocked, making progress"        |
| `adhd_post`            | Post generic message             | Sharing a thought with the group                   |
| `adhd_read`            | Read/filter messages             | Catching up on what you missed                     |
| `adhd_send`            | Send request to specific agent   | "Hey, can you help me with...?"                    |
| `adhd_archive`         | Archive old messages             | Cleaning up your workspace                         |
| `adhd_main_check`      | Check active supporter sessions  | Who's monitoring the room                          |

## Installation

ADHD is distributed as a Python package. The `.mcp.json` in the repo root auto-starts the MCP server when Claude Code opens the project.

```bash
# Clone the repo
git clone https://github.com/brainxio/attention-deficit-hyperactivity-driver

# Install the package
uv pip install -e .
```

## Usage

### Check active supporter sessions

```
adhd_main_check
```

### Send a message to all agents

```
adhd_send(to="all", message="Need help with tests", topic="help")
```

### Read recent activity

```
adhd_read(limit=20)
```

## Bus Path Convention

The bus lives at `~/.brainxio/adhd/{repo-slug}/bus.jsonl`. This centralizes coordination state outside any single repo and enables cross-repo sessions to share a bus.

### Environment Variables

| Variable                | Purpose                                     |
| ----------------------- | ------------------------------------------- |
| `ADHD_BUS_PATH`         | Absolute path override for advanced use     |
| `ADHD_BUS_REPO_SLUG`    | Join a specific repo's bus from any session |
| `ADHD_ENABLE_SUPPORTER` | Mark this session as a supporter (additive) |

### Cross-Repo Coordination

Set `ADHD_BUS_REPO_SLUG=projects` when in `ai-o4a/` to join the master coordination bus:

```bash
ADHD_BUS_REPO_SLUG=projects uv run adhd-mcp
```

## Design Philosophy

**Simple over smart.** The bus is append-only JSONL. No server, no database, no network. If it works for `git reflog`, it works for agent coordination.

**Explicit over automatic.** Supporter sessions are opted in via `ADHD_ENABLE_SUPPORTER=1`. Any number of supporters can coexist — they monitor, archive, and nudge without exclusive locks.

**Graceful degradation.** If the bus is missing, agents continue working solo. They just can't coordinate.

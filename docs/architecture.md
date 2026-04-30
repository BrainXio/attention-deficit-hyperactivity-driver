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

The bus lives at `~/.brainxio/adhd/{repo-slug}/bus.jsonl`. This centralizes coordination state outside any single repo, enabling cross-repo sessions to share a bus. The repo slug is derived from the git toplevel directory name, overridable via `ADHD_BUS_REPO_SLUG`.

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
  .mcp.json             # MCP server registration
  .gitignore
  ~/.brainxio/adhd/
    {repo-slug}/
      bus.jsonl          # The bus (outside any repo)
      bus_archive_*.jsonl # Old messages
```

## Environment Variables

| Variable                | Purpose                                                    |
| ----------------------- | ---------------------------------------------------------- |
| `ADHD_BUS_PATH`         | Absolute path to bus file (overrides all derivation)       |
| `ADHD_BUS_REPO_SLUG`    | Repo key in `.brainxio/adhd/` (default: git toplevel name) |
| `ADHD_SESSION_ID`       | Fixed session identifier (default: random 8-char UUID)     |
| `ADHD_AGENT_ID`         | Agent identifier (default: `agent-{session_id}`)           |
| `ADHD_ENABLE_SUPPORTER` | Set to `1` to mark session as a supporter (additive)       |

### Cross-Repo Coordination

To join another repo's bus from any session:

```bash
ADHD_BUS_REPO_SLUG=projects uv run adhd-mcp
```

This is useful when `ai-o4a/` agents need to coordinate with the master `projects` bus.

## MCP Server

The sole interface is `adhd-mcp`, a FastMCP stdio server. All agent interactions go through MCP tools with JSON schema validation, auto-discovery, and server-managed lifecycle.

### Tools

| Tool              | Purpose                         |
| ----------------- | ------------------------------- |
| `adhd_signin`     | Register session on the bus     |
| `adhd_signout`    | Deregister session              |
| `adhd_read`       | Read/filter messages            |
| `adhd_post`       | Post a generic message          |
| `adhd_send`       | Send message to specific agent  |
| `adhd_main_check` | Check active supporter sessions |
| `adhd_validate`   | Validate bus integrity          |
| `adhd_archive`    | Archive old messages            |
| `adhd_resolve`    | Print canonical bus path        |

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

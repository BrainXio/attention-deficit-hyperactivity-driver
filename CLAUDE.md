# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ADHD (Attention Deficit Hyperactivity Driver) is the **coordination nervous system** for the BrainXio ecosystem. It provides an append-only JSONL message bus at `~/.brainxio/adhd/` that all agent sessions read and write to, enabling inter-agent communication without a server, database, or network.

It exposes an **MCP server** (`adhd-mcp`) — other packages (Another-Intelligence, OCD, ASD) and Claude Code sessions interact with the bus exclusively through MCP tool calls. No package imports ADHD; all communication goes through the MCP registry.

## Build & Test Commands

```bash
cd attention-deficit-hyperactivity-driver

# Python environment (uv only — never pip)
uv sync
uv pip install -e ".[dev]"

# Run tests
uv run pytest -q
uv run pytest -q tests/test_bus.py                          # single file
uv run pytest --cov=src/adhd --cov-report=term-missing      # with coverage

# Lint & format
uv run ruff check .
uv run ruff format --check .

# Type check
uv run mypy src/adhd/ --strict

# MCP server (stdio — one per session)
uv run adhd-mcp

# Format markdown docs
uv run mdformat --check CONTRIBUTING.md docs/
```

Coverage minimum: **80%**.

## Architecture

```
src/adhd/
  __init__.py         # Package marker
  bus.py              # Core business logic — all bus I/O, protocols, validation
  mcp_server.py       # FastMCP server — sole interface, no CLI, no scripts
  models.py           # Pydantic models for bus messages and configuration
  notifications.py    # Desktop + Telegram notification helpers
  rules.py            # Protocol rules for self-describing bus (adhd_get_rules)
scripts/
  detect-perf-level.py  # Hardware probe for perf_level suggestion
  hitl-notify.py        # HITL decision polling daemon
```

### Bus File

Append-only JSONL at `~/.brainxio/adhd/{slug}/bus.jsonl`. Path resolution:

1. `ADHD_BUS_PATH` env var (storage directory prefix, default `~/.brainxio/adhd/`)
2. `ADHD_BUS_SLUG` env var (bus name, default: git toplevel basename)
3. Full path: `{ADHD_BUS_PATH}/{ADHD_BUS_SLUG}/bus.jsonl`

### Message Structure

Every message requires: `timestamp`, `session_id`, `agent_id`, `branch`, `type`, `topic`, `payload`.

### Protocols (all on the bus)

| Protocol         | Topic               | Key functions                                |
| ---------------- | ------------------- | -------------------------------------------- |
| Agent lifecycle  | `agent-lifecycle`   | signin, signout, heartbeat                   |
| Supporter        | `agent-lifecycle`   | `ADHD_ENABLE_SUPPORTER` flag, perf level     |
| MCP change       | `mcp-change`        | preparing/ready notifications                |
| Merge queue      | `merge-queue`       | claim/release with 5-min TTL                 |
| HITL             | `hitl-decisions`    | claim, release, RPE, approve, split, history |
| Subscription     | `bus-subscriptions` | subscribe/unsubscribe for push delivery      |
| Migration        | `bus-migration`     | poll-to-push migration with ack tracking     |
| Noise monitoring | `bus-noise`         | density warnings when thresholds exceeded    |

### MCP Tools (26 total)

**Lifecycle**: `adhd_signin`, `adhd_signout`, `adhd_start_heartbeat`
**Read/Write**: `adhd_read`, `adhd_post`, `adhd_send`
**Supporter**: `adhd_main_check`, `adhd_reap_stale`
**MCP Change**: `adhd_mcp_change_prepare`, `adhd_mcp_change_ready`, `adhd_mcp_change_check`
**HITL**: `adhd_human_claim_decision`, `adhd_human_release_decision`, `adhd_human_provide_rpe`, `adhd_human_approve_gonogo`, `adhd_human_split_duties`, `adhd_human_pending_decisions`, `adhd_human_decision_history`
**Push Delivery**: `adhd_subscribe`, `adhd_unsubscribe`, `adhd_poll`, `adhd_wait`, `adhd_migrate_to_push`
**Noise**: `adhd_noise_check`
**Maintenance**: `adhd_validate`, `adhd_archive`, `adhd_resolve`, `adhd_get_rules`

Protected types (`signin`, `signout`, `heartbeat`, `subscription`, `unsubscription`, `migration_announce`, `migration_ack`) and topics (`mcp-change`) cannot use `adhd_post` — they require dedicated tools.

## Development Conventions

- **Type hints mandatory** on all public functions and classes
- **Pydantic** for all configuration and data models
- **Tests use pytest** (not unittest)
- **Conventional Commits** — `feat(scope): description`, `fix(scope):`, `docs(scope):`, etc.
- **Worktrees required** for all development — never edit directly on main
- **No attribution** of any kind in commits, PRs, comments, or docs
- **Alphabetical ordering** for lists, tables, and directories unless semantic priority applies
- Line length: **100 characters**
- Ruff for linting/formatting, mypy with `--strict` for type checking
- When adding new message types, update `valid_types` in `bus.py`
- When adding new protocols, update `rules.py` and `docs/architecture.md`

## Key Documents

| Document               | Purpose                                             |
| ---------------------- | --------------------------------------------------- |
| `docs/architecture.md` | Bus design, components, env vars, message schema    |
| `docs/schema.md`       | Message schema reference                            |
| `CONTRIBUTING.md`      | Workflow, branch naming, PR process, conventions    |
| `tasks.json`           | Task tracker — pending, in-progress, completed work |

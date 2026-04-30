# Claude Code Activation

## Prerequisites

ADHD must be installed in the repository you are working on. The `.mcp.json` in the repo root references `adhd-mcp` from the local package.

If the repo already contains ADHD (e.g. the `brainxio/attention-deficit-hyperactivity-driver` repo itself), install it:

```bash
uv pip install -e .
```

If you are adding ADHD to a different repo, clone it first:

```bash
git clone https://github.com/brainxio/attention-deficit-hyperactivity-driver /tmp/adhd
uv pip install -e /tmp/adhd
```

## MCP Auto-Start

Claude Code reads `.mcp.json` from the repo root automatically. If the repo contains `.mcp.json` with the ADHD server definition, Claude Code starts the MCP server on project entry — no manual setup required.

## Available Tools

Once connected, these tools are available:

- `adhd_signin` — Sign in when your session starts
- `adhd_signout` — Sign out before your session ends
- `adhd_read` — Read recent messages from the bus
- `adhd_post` — Post a message to the bus
- `adhd_send` — Send a message to another agent
- `adhd_main_check` — Check who is main coordinator
- `adhd_main_claim` — Claim main coordinator role (requires ADHD_ALLOW_MAIN=1)
- `adhd_main_release` — Release main coordinator role
- `adhd_validate` — Validate bus integrity
- `adhd_archive` — Archive old messages

## Lifecycle

The MCP server handles signin, heartbeat, and signout automatically. Agents should still call `adhd_signin` at the start of their work and `adhd_signout` before exiting.

## Rules

- **Never** claim main session (`adhd_main_claim`) unless `ADHD_ALLOW_MAIN=1` is set.
- **Always** sign out before exiting.
- **Respond** to messages to you or "all".
- **Report** blockers immediately.

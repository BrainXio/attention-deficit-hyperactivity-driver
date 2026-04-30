# Cursor Activation

## Prerequisites

ADHD must be installed in the repository you are working on.

```bash
# Option A: Install from a local clone
git clone https://github.com/brainxio/attention-deficit-hyperactivity-driver /tmp/adhd
uv pip install -e /tmp/adhd

# Option B: Install from GitHub Packages (requires authentication)
uv pip install adhd --index-url https://pypi.pkg.github.com/brainxio
```

## Step 1: Add MCP Config

Create `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "adhd": {
      "command": "uv",
      "args": ["--directory", ".", "run", "adhd-mcp"]
    }
  }
}
```

## Step 2: Restart Cursor

The MCP server auto-starts when Cursor opens the project.

## Available Tools

Once connected, these tools are available:

- `adhd_signin` — Sign in when your session starts
- `adhd_signout` — Sign out before your session ends
- `adhd_read` — Read recent messages from the bus
- `adhd_post` — Post a message to the bus
- `adhd_send` — Send a message to another agent
- `adhd_main_check` — Check active supporter sessions
- `adhd_validate` — Validate bus integrity
- `adhd_archive` — Archive old messages

## Rules

- **Opt in** to supporter mode via `ADHD_ENABLE_SUPPORTER=1` if you want to monitor CI, archive the bus, or nudge stale agents.
- **Always** sign out before exiting.
- **Check** the bus before every commit or push.
- **Respond** to messages to you or "all".

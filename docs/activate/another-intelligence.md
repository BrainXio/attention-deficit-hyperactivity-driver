# Another Intelligence Activation

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

Add the ADHD server to your Another Intelligence settings:

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

## Step 2: Restart Session

The MCP server auto-starts when Another Intelligence opens the project.

## Available Tools

Once connected, these tools are available:

- `adhd_signin` — Sign in when your session starts
- `adhd_signout` — Sign out before your session ends
- `adhd_read` — Read recent messages from the bus
- `adhd_post` — Post a message to the bus
- `adhd_send` — Send a message to another agent
- `adhd_main_check` — Check who is main coordinator
- `adhd_main_claim` — Claim main coordinator role (human only)
- `adhd_main_release` — Release main coordinator role
- `adhd_validate` — Validate bus integrity
- `adhd_archive` — Archive old messages

## PPAC/RPE Integration

When the DigitalBrain decides, broadcast via `adhd_post`:

```json
{"type": "status", "topic": "agent-activity", "payload": {"state": "decided", "decision": "<summary>"}}
```

When recording RPE outcomes, broadcast via `adhd_post`:

```json
{"type": "event", "topic": "rpe-learning", "payload": {"context_key": "<key>", "rpe": 0.5, "outcome": "<result>"}}
```

## Rules

- **Never** claim main session.
- **Always** sign out before exiting.
- **Respond** to messages to you or "all".
- **Broadcast** RPE outcomes so other agents learn from your experience.
- **Respect** the main coordinator's decisions.

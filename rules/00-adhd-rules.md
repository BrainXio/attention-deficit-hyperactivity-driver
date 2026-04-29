# ADHD Rules

## Rule 1: Only Humans Claim Main

Agents must never claim the main coordinator role. Only a human user can call `adhd_main_claim`. This prevents coordination chaos when multiple agents start simultaneously.

## Rule 2: Always Sign Out

When a session ends (normally or abnormally), it must write a `signout` message. The MCP server attempts to write a signout on process exit.

## Rule 3: Heartbeats Are Mandatory

Every active session should maintain a heartbeat. The MCP server can manage this automatically via `adhd_start_heartbeat`. If the heartbeat stops, the agent is considered dead.

## Rule 4: Respect Topic Filtering

When reading the bus, filter by `topic` and `type`. Do not read every message. Topics:

- `agent-lifecycle` — signin, signout, heartbeat
- `coordination` — main session claims/releases
- `agent-activity` — status, tool_use, event
- `agent-request` — request, response, question, answer
- `schema` — API schema declarations
- `dependency` — Dependency graph updates

## Rule 5: Archive Regularly

When the bus exceeds 10,000 lines, run `adhd_archive` to archive old messages. This prevents unbounded growth and keeps reads fast.

## Rule 6: Validate Before Commit

Before pushing code that writes to the bus, run `adhd_validate` to ensure no corrupt lines were introduced.

## Rule 7: Payloads Must Be Objects

The `payload` field must always be a JSON object (`{}`), never a string or array. This allows consistent filtering and extension.

## Rule 8: Use Session IDs Consistently

The `session_id` must remain constant for the lifetime of a session. It is derived from `ADHD_SESSION_ID` environment variable, or a random UUID if not set.

## Rule 9: Branch Names Are Required

Always include the current git branch in the `branch` field. This helps the main session track which worktrees are active.

## Rule 10: Main Session Releases on Exit

When the main session ends, it must call `adhd_main_release` to free the coordinator role. Otherwise, new sessions will think a coordinator exists when it doesn't.

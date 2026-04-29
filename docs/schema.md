# Bus Message Schema

## Required Fields

Every message on the bus must be a single-line JSON object with these fields:

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

| Field | Type | Description |
|---|---|---|
| `timestamp` | string (ISO 8601) | When the message was sent |
| `session_id` | string | Unique session identifier |
| `agent_id` | string | Agent identifier (worktree name or feature) |
| `branch` | string | Git branch being worked on |
| `type` | string | Message type (see below) |
| `topic` | string | Message topic for filtering |
| `payload` | object | Arbitrary JSON payload |

## Message Types

### Lifecycle

| Type | Description | Payload |
|---|---|---|
| `signin` | Agent session started | `{ "pid": 1234 }` |
| `signout` | Agent session ended | `{}` |
| `heartbeat` | Periodic alive signal | `{ "pid": 1234 }` |

### Coordination

| Type | Description | Payload |
|---|---|---|
| `main_session_set` | User claimed coordinator role | `{}` |
| `main_session_released` | Coordinator stepped down | `{}` |

### Activity

| Type | Description | Payload |
|---|---|---|
| `status` | Agent reports current state | `{ "state": "working", "action": "writing tests" }` |
| `tool_use` | Agent used a tool | `{ "tool": "git.commit" }` |
| `event` | Generic event occurred | `{ "event": "ci-failure" }` |

### Communication

| Type | Description | Payload |
|---|---|---|
| `request` | Ask another agent for help | `{ "recipient": "all", "message": "..." }` |
| `response` | Reply to a request | `{ "recipient": "agent-id", "message": "..." }` |
| `question` | Blocking question | `{ "recipient": "main", "message": "..." }` |
| `answer` | Answer to question | `{ "recipient": "agent-id", "message": "..." }` |

### Schema

| Type | Description | Payload |
|---|---|---|
| `schema` | Shared API schema | `{ "api": "brain.decide", "signature": "..." }` |
| `dependency` | Declare dependency | `{ "needs": "feat/brain-regions", "provides": "feat/cli-commands" }` |

---
name: adhd-poster
description: Post a message to the ADHD coordination bus
argument-hint: --type TYPE --topic TOPIC [--payload JSON]
title: ADHD Poster
aliases: [Post Message, Send Update, ADHD Post]
tags: [skill, adhd, coordination]
created: 2026-04-29
updated: 2026-04-29
---

# ADHD Poster

Post a message to the ADHD multi-agent coordination bus.

## Behavior

Append a JSON message to the shared bus file. All agents in the same
repository read from this file.

## MCP Tool

```
adhd_post(type="status", topic="agent-activity", payload='{"state":"working","action":"writing tests"}')
```

## Parameters

| Parameter | Description         | Required              |
| --------- | ------------------- | --------------------- |
| `type`    | Message type        | Yes                   |
| `topic`   | Message topic       | Yes                   |
| `payload` | JSON string payload | No (defaults to `{}`) |

## Examples

Report status:

```
adhd_post(
    type="status",
    topic="agent-activity",
    payload='{"state":"ready-for-review","pr":"#15"}'
)
```

Log tool use:

```
adhd_post(
    type="tool_use",
    topic="agent-activity",
    payload='{"tool":"git.commit","files":"src/brain.py"}'
)
```

Declare schema:

```
adhd_post(
    type="schema",
    topic="brain-api",
    payload='{"api":"decide","signature":"async def decide(query: str) -> Decision"}'
)
```

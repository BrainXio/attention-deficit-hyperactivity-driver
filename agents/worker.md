---
name: worker
description: Standard worker agent in a multi-agent session
title: Worker Agent
aliases: [Feature Agent, Worktree Agent]
tags: [agent, bus, coordination]
created: 2026-04-29
updated: 2026-04-29
---

# Worker Agent

## Role

A Worker Agent is any Claude Code session working on a feature branch or
worktree. It collaborates with other workers via the bus and defers to
the Coordinator Agent.

## Startup Checklist

```
1. Sign in to bus: adhd_signin
2. Read recent activity: adhd_read(limit=20)
3. Check who is main: adhd_main_check
4. Announce task: adhd_post(type="status", topic="agent-activity", payload={"task":"..."})
5. Start working
```

## Communication Patterns

### Reporting Progress

```
adhd_post(
    type="status",
    topic="agent-activity",
    payload='{"state":"working","task":"Implementing RPE engine","progress":50}'
)
```

### Asking for Help

```
adhd_send(
    to="all",
    message="Stuck on MCP stdio handshake, anyone familiar?",
    topic="help"
)
```

### Declaring Dependencies

```
adhd_post(
    type="dependency",
    topic="dependency-graph",
    payload='{"needs":"feat/permissions-engine","provides":"feat/mcp-client"}'
)
```

### Logging Tool Use

```
adhd_post(
    type="tool_use",
    topic="agent-activity",
    payload='{"tool":"git.commit","message":"feat: add MCP client"}'
)
```

## Shutdown Checklist

```
1. Report completion: adhd_post(type="status", topic="agent-activity", payload='{"state":"done"}')
2. Sign out: adhd_signout
3. If you were main, release: adhd_main_release
```

## Rules

- Always sign in before working
- Check bus before making breaking changes
- Respond to questions from other agents
- Report blockers immediately
- Never claim main session

---
name: adhd-reader
description: Read and filter messages from the ADHD coordination bus
argument-hint: '[--limit N] [--type TYPE] [--topic TOPIC] [--agent AGENT]'
title: ADHD Reader
aliases: [Read Bus, Check Messages, ADHD Read]
tags: [skill, adhd, coordination]
created: 2026-04-29
updated: 2026-04-29
---

# ADHD Reader

Read recent messages from the ADHD multi-agent coordination bus.

## Behavior

Query the append-only bus file for messages matching the given filters.

## MCP Tool

```
adhd_read(limit=20)
adhd_read(type="heartbeat", topic="agent-lifecycle")
adhd_read(agent="feat/docker-image")
```

## Parameters

| Parameter | Description            | Default |
| --------- | ---------------------- | ------- |
| `limit`   | Number of messages     | 50      |
| `type`    | Filter by message type | All     |
| `topic`   | Filter by topic        | All     |
| `agent`   | Filter by agent ID     | All     |

## Examples

Check who is main:

```
adhd_read(type="main_session_set", topic="coordination")
```

See recent heartbeats:

```
adhd_read(type="heartbeat", limit=10)
```

Check agent activity:

```
adhd_read(topic="agent-activity", limit=20)
```

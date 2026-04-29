---
name: adhd-main
description: Manage the main coordinator session for ADHD multi-agent coordination
argument-hint: "[--claim|--check|--release|--elect]"
title: "ADHD Main Session"
aliases: ["Main Session", "Coordinator", "ADHD Coordinator"]
tags: [skill, adhd, coordination]
created: 2026-04-29
updated: 2026-04-29
---

# ADHD Main Session

Manage the main coordinator session for ADHD multi-agent coordination.

## Behavior

The main session acts as the central coordinator. Only one session may hold the main role at a time. Agents must check who is main before taking unilateral action.

## MCP Tools

- `adhd_main_claim` — Claim coordinator role
- `adhd_main_check` — Check who is coordinator
- `adhd_main_release` — Release coordinator role
- `adhd_main_elect` — Auto-elect oldest active session

## Important

Only a human user should claim the main session. Agents must never self-elect.

## Examples

Start coordinating:
```
adhd_main_claim
```

Check status:
```
adhd_main_check
```

Release when done:
```
adhd_main_release
```

Force election (if main is dead):
```
adhd_main_elect
```

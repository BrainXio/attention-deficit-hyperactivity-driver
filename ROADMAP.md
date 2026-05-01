# ADHD Roadmap

## Phase 1: Core Bus (Complete)

- [x] Append-only JSONL bus with resolve, I/O, validation, archival
- [x] MCP server with signin, signout, heartbeat lifecycle
- [x] Supporter model (`ADHD_ENABLE_SUPPORTER`) replacing exclusive coordinator
- [x] MCP change notification protocol (preparing/ready)
- [x] Merge-queue claim protocol (claim/release with 5-min TTL)
- [x] Bus path resolution for git submodules and worktrees
- [x] Human-In-The-Loop (HITL) protocol — claim, release, RPE, Go/NoGo, split duties
- [x] HITL notification system (desktop + Telegram fallback)
- [x] Perf level detection and heartbeat payload integration
- [x] Stale heartbeat reaper (15-min threshold auto-signout)
- [x] Recipient filter on `adhd_read` (exact match + "all" wildcard)
- [x] Push/event-driven delivery — subscribe, unsubscribe, poll, wait, migrate_to_push
- [x] Agent noise-threshold monitoring — density warnings, `adhd_noise_check`

**Delivered**: 26 MCP tools, 8 protocols, 172 tests, 84% coverage, mypy strict.

## Phase 2: Hardening & Scale

### Auth & Identity

- [ ] Agent capability tokens — signed claims so agents can prove what they're authorized to do
- [ ] Agent verification — cryptographic identity beyond session ID, preventing impersonation
- [ ] Bus access control — read-only vs read-write agent roles

### Bus Integrity

- [ ] Message signing — HMAC or Ed25519 on each line to detect tampering
- [ ] Causal ordering — Lamport clocks or vector clocks for partial message ordering
- [ ] Bus snapshots — periodic full-state checkpoints for faster recovery and replay

### Multi-Bus Federation

- [ ] Cross-bus bridging — forward messages between buses for multi-repo workflows
- [ ] Bus discovery — `adhd_discover` tool to find active buses on the machine
- [ ] Namespace routing — route messages by project/bus namespace

## Phase 3: Ecosystem Integration

### Another-Intelligence (Cerebro)

- [ ] Cerebro startup protocol — auto-signin, heartbeat, and rules query on brain boot
- [ ] PPAC decision broadcasting — structured decision messages on the bus
- [ ] Cross-agent RPE sharing — agents learn from each other's reward prediction errors

### OCD Integration

- [ ] Protocol compliance auditing — OCD reads the bus and flags violations
- [ ] Rule synchronization — OCD rules propagate to agents via bus messages
- [ ] Mode switching — OCD broadcasts mode changes (strict/relaxed/off)

### ASD Integration

- [ ] Knowledge compilation triggers — ASD ingests bus conversations into long-term memory
- [ ] Semantic query protocol — agents query ASD's KB through bus messages
- [ ] Cross-session context preservation — ASD remembers past conversations for continuity

## Phase 4: Advanced Protocols

### Task Coordination

- [ ] Work allocation protocol — supporters post available tasks, agents claim them on the bus
- [ ] Dependency tracking — agents declare what they depend on and what they produce
- [ ] Merge coordination — multi-PR orchestration across repos

### Observability

- [ ] Bus metrics dashboard — Prometheus/Grafana metrics from bus activity
- [ ] Agent health scoring — composite health metric from heartbeat, responsiveness, error rate
- [ ] Anomaly detection — pattern-based detection of agent misbehavior or bus abuse
- [ ] Bus replay — time-travel debugging by replaying bus history

### Protocol Evolution

- [ ] Schema versioning — formal version negotiation between agents and bus
- [ ] Deprecation protocol — graceful phase-out of old message types
- [ ] Extension registry — agents can register custom protocols without core changes

## Non-Goals

- **Network transport** — the bus is file-based by design. No gRPC, no WebSocket server, no TCP.
- **Database backend** — JSONL is the storage format. No Postgres, no SQLite, no Redis.
- **Real-time guarantees** — best-effort delivery with file watching. Not a message queue.
- **Agent implementation** — ADHD coordinates agents; it does not implement them. That's Another-Intelligence's job.

## Versioning

| Version | Scope                                                 |
| ------- | ----------------------------------------------------- |
| 0.1.0   | Phase 1 — Core bus (current)                          |
| 0.2.0   | Phase 2 — Auth, integrity, multi-bus                  |
| 0.3.0   | Phase 3 — Full ecosystem integration                  |
| 1.0.0   | Phase 4 — Task coordination, observability, evolution |

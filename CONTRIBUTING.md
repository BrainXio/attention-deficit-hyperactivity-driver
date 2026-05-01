# Contributing to ADHD

## Development Environment

Python 3.12+, managed with [uv](https://docs.astral.sh/uv/):

```bash
cd attention-deficit-hyperactivity-driver
uv sync
uv pip install -e ".[dev]"
```

## Branch Naming

Use conventional prefix and a short kebab-case description:

| Prefix      | When to use                               |
| ----------- | ----------------------------------------- |
| `feat/`     | New feature or enhancement                |
| `fix/`      | Bug fix                                   |
| `docs/`     | Documentation changes only                |
| `chore/`    | Maintenance, tooling, CI, dependencies    |
| `refactor/` | Code restructuring without feature change |
| `test/`     | Test additions or improvements            |
| `ci/`       | CI/CD changes                             |

Examples: `feat/recipient-filter`, `fix/bus-path-resolution`, `docs/add-hitl-workflow`.

All development happens in git worktrees created from main. Never edit directly on main
outside of urgent hotfixes.

### Worktree Setup

```bash
ocd worktree new <short-kebab-description>
git merge main
```

After the branch merges, remove the worktree:

```bash
ocd worktree remove <slug>
```

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`, `ci`, `perf`.

Scopes: `bus`, `mcp`, `hitl`, `heartbeat`, `supporter`, `adhd`, `docs`.

Examples:

- `feat(bus): add recipient filter to adhd_read`
- `fix(bus): handle empty bus file gracefully`
- `docs(bus): add heartbeat protocol sequence diagram`

Keep descriptions concise and imperative. No attribution of any kind — commits must
read as if written by a human developer with no outside assistance.

## PR Workflow

1. Create a feature branch from `main`

2. Implement with tests (code coverage minimum 80%)

3. Run the local CI gate before pushing:

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run pytest -q
   uv run mypy src/adhd/ --strict
   ```

4. Push and open a PR against `main`

5. Add labels at creation time (at least one required):

   | Prefix    | Primary label | Additional labels                      |
   | --------- | ------------- | -------------------------------------- |
   | feat:     | enhancement   | + documentation if docs/ changed       |
   | fix:      | bug           |                                        |
   | docs:     | documentation |                                        |
   | ci:       | ci            | + github-actions if workflows/ changed |
   | refactor: | enhancement   |                                        |
   | test:     | ci            |                                        |

6. Post the PR URL to the ADHD bus for review

7. Do not self-merge — wait for a supporter review

8. After merge, pull main immediately and remove the worktree

### PR Body Template

```
## Summary

1-3 bullet points describing what changed and why.

## Test plan

- [ ] Checklist of verification steps
- [ ] Include both automated (CI) and manual checks
```

## Code Style

- Type hints on all public functions and classes
- Line length: 100 characters
- Use Pydantic for configuration and data models
- Tests use `pytest` (not `unittest`)
- Imports sorted via `ruff` (enforced in CI)
- Lists, tables, and directories use alphabetical ordering unless semantic priority applies
- No attribution of any kind in commits, PRs, comments, or docs

## Running the MCP Server

```bash
uv run adhd-mcp
```

The server communicates over stdio. It is a FastMCP process tied to one session —
it cannot push to other sessions directly.

## Testing

```bash
uv run pytest -q                          # all tests
uv run pytest -q tests/test_bus.py        # single file
uv run pytest --cov=src/adhd --cov-report=term-missing   # with coverage
```

Coverage minimum: 80%. New features must include tests for normal operation,
threshold-exceeded, and edge cases.

## Bus Protocol Conventions

### Message Structure

Every bus message requires: `timestamp`, `session_id`, `agent_id`, `branch`, `type`,
`topic`, `payload`.

### Protected Types and Topics

Protected message types must use dedicated tools, not `adhd_post`:

| Type                 | Dedicated tool                       |
| -------------------- | ------------------------------------ |
| `signin`             | `adhd_signin`                        |
| `signout`            | `adhd_signout`                       |
| `heartbeat`          | Automatic via `adhd_start_heartbeat` |
| `subscription`       | `adhd_subscribe`                     |
| `unsubscription`     | `adhd_unsubscribe`                   |
| `migration_announce` | `adhd_migrate_to_push`               |
| `migration_ack`      | `adhd_migrate_to_push` (internal)    |

Protected topics must use dedicated tools, not `adhd_post`:

| Topic        | Dedicated tools                                     |
| ------------ | --------------------------------------------------- |
| `mcp-change` | `adhd_mcp_change_prepare` / `adhd_mcp_change_ready` |

### Protocols

| Protocol         | Topic               | Purpose                                          |
| ---------------- | ------------------- | ------------------------------------------------ |
| Agent lifecycle  | `agent-lifecycle`   | signin, signout, heartbeat                       |
| Supporter        | `agent-lifecycle`   | `ADHD_ENABLE_SUPPORTER` flag, perf level         |
| MCP change       | `mcp-change`        | preparing/ready notifications for server updates |
| Merge queue      | `merge-queue`       | claim/release with 5-min TTL                     |
| HITL             | `hitl-decisions`    | claim, release, RPE, approve, split, history     |
| Subscription     | `bus-subscriptions` | subscribe/unsubscribe for push delivery          |
| Migration        | `bus-migration`     | poll-to-push migration with ack tracking         |
| Noise monitoring | `bus-noise`         | density warnings when thresholds exceeded        |

### General Rules

- Bus is append-only — never delete or edit existing messages
- When adding new message types, update `valid_types` in `bus.py`
- When adding new protocols, update `rules.py` and `docs/architecture.md`
- Use `recipient` in payload for targeted delivery; `"all"` for broadcasts

## Documentation Sync

After shipping a feature that adds or changes infrastructure, update:

1. `docs/reference/README.md` — add entries to relevant registry tables
2. `docs/planning.md` — mark shipped items as done
3. `tasks.json` — move completed items and update status

## Getting Help

This repo is *itself* the coordination bus. For questions, post `type: question` to
the ADHD bus. For protocol violations, OCD will catch them.

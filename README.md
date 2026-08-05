# Research OS

Persistent research environment for long-term mathematical exploration.

**Goal:** maximize verified knowledge accumulation, not “solve the conjecture.”

## Locked decisions (v0.1)

| Topic | Decision |
|-------|----------|
| Repository | `research-os` (this repo) |
| Canonical store | SQLite |
| Formal verification | Deferred (no Lean/Isabelle in P0–P2) |
| Logical equivalence | Equivalence classes (see `docs/decisions/002-equivalence-classes.md`) |
| Human interface | Obsidian vault only |
| Models | Configurable per role; discovered via Cursor SDK when live workers run |
| Git | One commit per accepted transaction |

## Architecture

```
Human → Scheduler → Agents → Research MCP → Knowledge Graph → Obsidian → Git
```

Agents never write markdown or touch the filesystem. All mutations go through MCP.

See `docs/architecture/` and `docs/decisions/`.

## Status

**P0 — Kernel**

- Immutable transaction kernel with invariant enforcement
- SQLite canonical store and versioned migrations
- Role-scoped MCP server
- Obsidian vault projection
- Git commit bridge (enabled in runtime; disabled in tests)

**P1 — Report intake and deterministic Reviewer**

- Immutable worker reports with review decisions
- `submit_report`, `get_report`, `list_pending_reports`, `review_report` MCP tools
- Deterministic anti-slop gates (`configs/anti_slop.yaml`)
- Reviewer adjudication compiles accepted claims into invariant-enforced transactions
- Readable report/review notes under `vault/03_reports/`

**P2 — Scheduler, Worker runtime, activity panel**

- Job/run/event/budget ledger in SQLite
- Minimal scheduler (`dispatch_worker`) with fake SDK for offline CI
- Optional live Cursor SDK worker (`pip install -e ".[sdk]"`, `CURSOR_API_KEY`)
- Model profile validation via `Cursor.models.list()`
- Isolated per-run sandbox with fail-closed Cursor hooks (MCP-only)
- Auto-refreshed human-readable panel at `vault/00_meta/AGENT_ACTIVITY.md`

**P3 — Human-in-the-loop and Thinker**

- Human operator MCP tools: `pin_node`, `freeze_node`/`unfreeze_node`, `inject_literature`, `override_budget`, `resolve_needs_human`
- Thinker agent + `dispatch_thinker` scheduler tool for periodic global synthesis passes

**P4 — Search, dedup, lifecycle**

- Embedding-backed semantic search/read tools (`semantic_search`, `find_similar`, `find_orphans`, `find_dead_nodes`, `timeline`, `nearest_main`, `search_by_definition`, `search_counterexamples`, `search_techniques`)
- Duplicate detection and equivalence-class merge (`find_duplicate`, `merge_duplicate`) — textual/semantic similarity only, never gates acceptance
- Automatic superseding and `STUCK` lifecycle wiring

**P5 — Vault v2, activity v2, operator CLI**

- `vault/00_meta/STATISTICS.md` and `TIMELINE.md`, regenerated on every accepted transaction
- Activity dashboard "Needs human" section for `NEEDS_HUMAN` reports
- Operator CLI (`ros`) — see [`docs/RUNNING.md`](docs/RUNNING.md)

**P6 — Formal export scaffold**

- `export_formal` MCP tool renders a non-gating, explicitly "NOT VERIFIED" Lean-style text stub. It never sets verification status — acceptance remains a Reviewer decision.

**P7 — Longevity and unattended operation**

- Scheduler daemon (`research-os-scheduler`) for continuous polling/dispatch
- Backup/restore (`ros backup`, `ros restore`) via online SQLite snapshots + vault manifest
- Weekly analytics report (`ros weekly-report`) — review throughput, budget burn, research velocity

**Deferred:** Obsidian TypeScript plugin (P5.1), SQLite→Postgres scale evaluation (P7.4), chaos/load testing (P7.5).

**Constraint honored throughout P3-P7:** proof/counterexample acceptance is always a Reviewer decision (deterministic anti-slop + LLM/human judgment). Nothing added performs numeric/mechanical verification — embedding search is textual similarity only, auto-superseding is structural bookkeeping, and formal export never gates anything.

## P1–P2 completion notes

- Normalized immutable report entities: `report_claims`, `citations`, `candidate_operations`
- Review outcomes: `ACCEPT`, `PARTIAL_ACCEPT`, `REJECT`, `NEEDS_HUMAN` with claim indices
- Run/job lifecycle states: `QUEUED` … `CANCELLED`
- Typed MCP tools returning structured models (not JSON strings)
- Budget enforcement via `consume_budget`
- Projection replay via `replay_projection`
- Activity panel writes atomically; `AGENT_ACTIVITY.md` is gitignored

## Setup and running

See [`docs/RUNNING.md`](docs/RUNNING.md) for full setup, the MCP server, the
`ros` operator CLI, the scheduler daemon, backups, and — importantly — how to
connect Codex CLI, Cursor, or GitHub Copilot to this project's MCP server
(config files for all three are already checked in under `.vscode/`,
`.cursor/`, and `.codex/`).

Quick start:

```powershell
cd C:\!PROG\research-os
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

Locked dependencies are recorded in `requirements.lock`.

### Report flow

1. Worker investigates a frontier node and calls `submit_report`.
2. Reviewer (or human) calls `review_report`.
3. Deterministic anti-slop gates run before any knowledge-graph mutation.
4. Accepted claims compile into `apply_transaction` operations.
5. Vault projection and optional Git commit follow accepted transactions.

### Scheduler dispatch

```json
{"role": "scheduler", "run_id": "run_sched_1", "node_id": "ros_mc_..."}
```

via MCP tool `dispatch_worker`. Offline tests use a fake SDK adapter; production can enable the live Cursor SDK with `RESEARCH_OS_USE_LIVE_SDK=1`.

### Agent activity panel

Open `vault/00_meta/AGENT_ACTIVITY.md` in Obsidian. The projection service refreshes it on run state changes and heartbeats. It is prose-only operational state, not mathematical knowledge, and is not committed to Git on every heartbeat.

## Model selection

Edit `configs/models.yaml` to choose Worker / Reviewer / Thinker profiles. Before a live worker launch, Research OS validates the configured model id against `Cursor.models.list()` and records the resolved profile in the run ledger.

## Layout

- `docs/` — architecture, ADRs, and [`RUNNING.md`](docs/RUNNING.md) (setup/run guide)
- `schemas/` — JSON schemas for objects, edges, events, reports
- `configs/` — roles, models, frontier, budgets, anti-slop, activity
- `src/research_os/` — kernel, store, MCP, projection, scheduler, agents, CLI, daemon, backup, analytics
- `vault/` — Obsidian projection (generated; do not hand-edit)
- `data/canonical/` — SQLite database (not committed)
- `tests/` — invariant, reviewer, scheduler, migration, and activity tests

## Testing and operational recovery

See [`docs/RUNNING.md`](docs/RUNNING.md) for the full test commands and the
operational recovery runbook (stale workers, rejected reports, disaster
recovery via `ros backup`/`ros restore`).

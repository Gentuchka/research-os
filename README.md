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

**Deferred to P3+:** weighted frontier optimization, Thinker global passes, embedding-backed semantic dedup, custom Obsidian plugin.

## P1–P2 completion notes

- Normalized immutable report entities: `report_claims`, `citations`, `candidate_operations`
- Review outcomes: `ACCEPT`, `PARTIAL_ACCEPT`, `REJECT`, `NEEDS_HUMAN` with claim indices
- Run/job lifecycle states: `QUEUED` … `CANCELLED`
- Typed MCP tools returning structured models (not JSON strings)
- Budget enforcement via `consume_budget`
- Projection replay via `replay_projection`
- Activity panel writes atomically; `AGENT_ACTIVITY.md` is gitignored

## Setup

Requires Python 3.12+.

```powershell
cd C:\!PROG\research-os
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

For live Cursor SDK workers:

```powershell
pip install -e ".[dev,sdk]"
$env:CURSOR_API_KEY = "cursor_..."
$env:RESEARCH_OS_USE_LIVE_SDK = "1"
```

Locked dependencies are recorded in `requirements.lock`.

## MCP server

```powershell
research-os-mcp
```

Or:

```powershell
python -m research_os.mcp_server.server
```

Set `RESEARCH_OS_REPO` when launching MCP from a worker sandbox so the server points at the real canonical store.

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

- `docs/` — architecture and ADRs
- `schemas/` — JSON schemas for objects, edges, events, reports
- `configs/` — roles, models, frontier, budgets, anti-slop, activity
- `src/research_os/` — kernel, store, MCP, projection, scheduler, agents
- `vault/` — Obsidian projection (generated; do not hand-edit)
- `data/canonical/` — SQLite database (not committed)
- `tests/` — invariant, reviewer, scheduler, migration, and activity tests

## Testing

```powershell
pytest -q
ruff check src tests
```

Optional live SDK smoke test (requires network + API key):

```powershell
$env:RESEARCH_OS_LIVE_SDK_TEST = "1"
pytest tests/test_live_sdk.py -q
```

## Operational recovery

- **Projection/Git failed after accepted DB commit:** inspect `transactions.projection_status` and replay projection from the accepted transaction payload.
- **Stale worker:** check `AGENT_ACTIVITY.md` Problems section and `agent_runs` / `agent_events` tables.
- **Rejected report:** see `vault/03_reports/` and `data/rejections/` for reason codes.

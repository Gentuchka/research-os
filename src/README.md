# Research OS (package)

Python package implementing the Research OS kernel and P1–P2 operational loop.

## Modules

- `kernel/` — invariant-enforced transactions, serialization, replay projection
- `store/` — SQLite repository, migrations, run lifecycle states
- `reports/` — immutable report intake with normalized claim/citation/candidate storage
- `reviewer/` — deterministic anti-slop adjudication (`ACCEPT`, `PARTIAL_ACCEPT`, `REJECT`, `NEEDS_HUMAN`)
- `scheduler/` — job/run orchestration with fake or live Cursor SDK workers
- `projection/` — Obsidian vault and activity panel projections
- `mcp_server/` — typed FastMCP tools and role ACL enforcement
- `budgets/` — node budget accounting via `consume_budget`

See the root [README.md](../../README.md) for setup and operator flow.

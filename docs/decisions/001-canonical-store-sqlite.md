# ADR 001: SQLite canonical store

## Status

Accepted

## Decision

Canonical knowledge graph and append-only event log live in **SQLite** at `data/canonical/research.db`.

## Rationale

- Single-user / single-machine research loop fits SQLite well.
- ACID transactions align with “one transaction = one atomic KG change.”
- No separate server to operate during P0–P3.
- Obsidian + Git remain the human-readable and audit layers.

## Schema outline (P0)

- `objects` — current snapshot per `ros_id` (status, type, content hash; statement in blob or side table)
- `object_versions` — immutable admitted content (Invariant 1)
- `edges` — typed mathematical edges
- `provenance_edges` — `prov:*` edges
- `equivalence_classes` — class id, representative `ros_id`
- `events` — append-only audit log
- `metrics` — append-only metric observations
- `budgets` — current budget counters per node
- `transactions` — accepted MCP transaction metadata + git commit sha

## Consequences

- Database file is gitignored; reproducibility comes from Git commits of vault + exported transaction log if needed.
- Postgres migration is a future ADR if multi-writer or remote agents are required.

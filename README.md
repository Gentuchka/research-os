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
| Models | Configurable per role; default GPT 5.6 Sol with selectable reasoning effort |
| Git | One commit per accepted transaction |

## Architecture

```
Human → Scheduler → Agents → Research MCP → Knowledge Graph → Obsidian → Git
```

Agents never write markdown or touch the filesystem. All mutations go through MCP.

See `docs/architecture/` and `docs/decisions/`.

## Status

**P0 — Kernel** (not started): schemas, SQLite store, invariant engine, MCP skeleton, git bridge.

## Layout

- `docs/` — architecture and ADRs
- `schemas/` — JSON schemas for objects, edges, events, reports
- `configs/` — roles, models, frontier, budgets, anti-slop
- `src/` — implementation (kernel, MCP, agents, projection)
- `vault/` — Obsidian projection (generated; do not hand-edit)
- `data/canonical/` — SQLite database (not committed)
- `tests/` — invariant and MCP tests

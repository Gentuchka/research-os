# Research OS architecture

This directory contains architecture notes for the Research OS implementation.

## Runtime flow

```
Scheduler -> Worker (fake or Cursor SDK) -> Research MCP -> Report intake
    -> Reviewer (deterministic anti-slop) -> Transaction kernel -> SQLite KG
    -> Obsidian projection + activity panel
```

## Canonical vs operational state

- **Canonical knowledge** lives in SQLite and is mutated only through invariant-checked transactions.
- **Operational state** (runs, jobs, events, budgets, activity panel) is derived and may be volatile.
- **Reports** are immutable once submitted; review decisions are append-only.

## Key artifacts

- `vault/02_objects/` — knowledge graph notes
- `vault/03_reports/` — report and review projections
- `vault/00_meta/AGENT_ACTIVITY.md` — live agent activity (gitignored)
- `data/rejections/` — exported rejection records

See `docs/decisions/` for locked architectural decisions.

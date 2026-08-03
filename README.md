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

**P0 — Kernel** implemented:

- Immutable transaction kernel with invariant enforcement
- SQLite canonical store and migrations
- Role-scoped MCP server (`apply_transaction`, `get_node`, `find_frontier`, `graph_statistics`, `history`)
- Obsidian vault projection
- Git commit bridge (enabled in runtime; disabled in tests)

**Deferred to P1+:** Worker/Reviewer/Thinker LLM loops, scheduler, anti-slop semantic checks, metrics engine automation.

## Setup

Requires Python 3.12+.

```powershell
cd C:\!PROG\research-os
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

## MCP server

```powershell
research-os-mcp
```

Or:

```powershell
python -m research_os.mcp_server.server
```

Configure Cursor MCP to launch `research-os-mcp` from this repo with `PYTHONPATH=src` if not installed editable.

### Example transaction (Reviewer role)

Use `apply_transaction` with JSON:

```json
{
  "summary": "Admit main conjecture",
  "ops": [
    {
      "op_type": "append_node",
      "object": {
        "id": "ros_mc_01EXAMPLE",
        "type": "MainConjecture",
        "title": "Goldbach",
        "statement": "Every even integer greater than 2 is the sum of two primes.",
        "status": "ACTIVE",
        "created_at": "2026-08-04T00:00:00+00:00",
        "information_gain": "Establishes the main research target.",
        "provenance": {
          "origin_kind": "human_directive",
          "origin_refs": ["bootstrap"],
          "created_by_run": "run_human_1"
        }
      }
    }
  ]
}
```

## Layout

- `docs/` — architecture and ADRs
- `schemas/` — JSON schemas for objects, edges, events, reports
- `configs/` — roles, models, frontier, budgets, anti-slop
- `src/research_os/` — kernel, store, MCP, projection, git bridge
- `vault/` — Obsidian projection (generated; do not hand-edit)
- `data/canonical/` — SQLite database (not committed)
- `tests/` — invariant and end-to-end tests

## Model selection

Edit `configs/models.yaml` to switch Worker / Reviewer / Thinker profiles (`gpt56_sol_medium`, `gpt56_sol_high`, `gpt56_sol_max`).

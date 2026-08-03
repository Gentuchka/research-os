# ADR 002: Equivalence classes instead of `equivalent_to` cycles

## Status

Accepted

## Context

The mathematical graph must stay acyclic (Invariant 4). One edge type is special:

**`equivalent_to`** — two statements say the same thing in different words, or are provably equivalent.

Example:

- Hypothesis A: “Every even integer > 2 is the sum of two primes.”
- Hypothesis B: “Goldbach’s conjecture holds for all even integers greater than 2.”

A and B are not parent/child. They are **the same claim**.

If we add `A equivalent_to B` and `B equivalent_to A` as normal directed edges, we create a **cycle**. The cycle checker would reject them, or we would need exceptions that weaken Invariant 4.

## Option A — Equivalence classes (chosen)

Do **not** store `equivalent_to` as graph edges between arbitrary nodes.

Instead:

1. Each admitted object has `equivalence_class_id` (nullable).
2. When Reviewer admits two equivalent statements, they assign the **same** class id (or merge classes).
3. The **mathematical DAG** only connects **class representatives** — one canonical node per class.
4. Non-representative members link to their class via `prov:member_of_class` (provenance), not a math edge.

```
Class EQ_01
  representative → Hypothesis A (ACTIVE, on frontier)
  members        → Hypothesis B (SUPERSEDED or ARCHIVED as duplicate)
```

**Distance, frontier, and metrics** are computed on representatives. Duplicates never fork the research tree.

**Supersession:** merging duplicates does not delete history. B remains in the graph with status `SUPERSEDED` and `supersedes` → A.

## Option B — Allow cycles only inside `equivalent_to` (rejected)

Keep `equivalent_to` as bidirectional edges and exempt that edge type from the global DAG rule.

Problems:

- Cycle detection becomes two-phase (harder to reason about).
- Path queries (“distance to main conjecture”) need SCC collapsing anyway.
- Easier for agents to accidentally create logical cycles mixed with equivalence.

## Decision

Use **equivalence classes (Option A)**.

## Consequences

- `equivalent_to` is removed from mathematical edge types; equivalence is a **structural field + provenance link**.
- `find_duplicate` and Reviewer anti-slop merge into class assignment, not edge creation.
- MCP tools: `merge_equivalence_class`, `get_class_members` (Reviewer only).

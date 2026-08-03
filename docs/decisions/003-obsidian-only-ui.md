# ADR 003: Obsidian-only human interface

## Status

Accepted

## Decision

Humans interact with Research OS through the **Obsidian vault** (`vault/`) and Git history. No web dashboard in P0–P3.

## Human actions (via MCP or thin operator scripts)

- Pin / freeze frontier nodes
- Inject literature (`Paper` objects)
- Override budgets
- Trigger Thinker run
- Approve exceptional transactions

Operator scripts call the same MCP tools as agents (role=`human`), not direct DB access.

## Consequences

- Projection layer must be complete enough for navigation: wikilinks, frontier page, timeline, statistics.
- Vault files are generated; hand-editing is overwritten on next projection (document this in `vault/00_meta/HOME.md`).

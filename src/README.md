# P0 Kernel — next implementation steps

1. `src/kernel/` — IDs, content hash, invariant engine, transaction builder
2. `src/store/` — SQLite schema + migrations
3. `src/mcp_server/` — tools with role ACL from `configs/roles.yaml`
4. `src/projection/` — Obsidian renderer
5. `src/git_bridge/` — commit per accepted transaction

No agent LLM code until P1 Reviewer loop with fixture reports.

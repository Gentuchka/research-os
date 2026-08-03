# ADR 005: One Git commit per accepted transaction

## Status

Accepted

## Decision

Every **accepted** MCP transaction produces exactly one Git commit containing:

- Updated vault projection files for affected objects
- Transaction metadata file under `data/transactions/{tx_id}.json` (committed)
- Commit message: `ros(tx): {tx_id} {short_summary}`

Rejected transactions are logged in SQLite only (optional export to `data/rejections/`).

## Consequences

- `git log` is the human timeline of verified knowledge changes.
- Rollback = revert commit + SQLite restore from backup or replay from events (replay tooling in P1).

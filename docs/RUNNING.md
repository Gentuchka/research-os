# Running Research OS

This is the practical "how do I actually run this" guide. For architecture and
the research plan see [`docs/architecture/`](architecture/) and
[`docs/P3-P7-PLANS.md`](P3-P7-PLANS.md).

## 1. First-time setup

Requires Python 3.12+.

```powershell
cd C:\!PROG\research-os
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

Optional, for live Cursor SDK worker runs instead of the offline fake adapter:

```powershell
pip install -e ".[dev,sdk]"
$env:CURSOR_API_KEY = "cursor_..."
$env:RESEARCH_OS_USE_LIVE_SDK = "1"
```

`RESEARCH_OS_REPO` controls which repo root the server/CLI/daemon read config
and data from. It defaults to this checkout, so you only need to set it when
launching from somewhere else (e.g. a worker sandbox).

## 2. Ways to run the system

Everything below is a thin wrapper over the same MCP tool layer, so behavior
(ACL, invariants, Reviewer gating) is identical no matter which entry point
you use.

### MCP server (what agents talk to)

```powershell
research-os-mcp
# or
python -m research_os.mcp_server.server
```

Talks stdio MCP. This is what Codex, Cursor, and GitHub Copilot connect to —
see [section 3](#3-connecting-an-ai-coding-agent).

### Operator CLI (`ros`)

A human-facing command line for the same tools, always running as
`role="human"`:

```powershell
ros pin <node_id> --weight 2
ros freeze <node_id> --reason "..."
ros unfreeze <node_id>
ros dispatch worker --node <node_id>
ros dispatch thinker
ros activity
ros resolve-report <report_id> --accept --note "..."
ros backup .\backups
ros restore .\backups\backup_<timestamp> [--force]
ros weekly-report [--days 7]
```

### Scheduler daemon (unattended operation)

Polls the frontier, dispatches workers up to a concurrency limit, and runs the
Thinker on a cadence, until stopped (Ctrl+C / SIGTERM):

```powershell
research-os-scheduler
# or
python -m research_os.daemon.scheduler_daemon
```

Configure via `configs/activity.yaml` under a `daemon:` key
(`poll_interval_seconds`, `max_concurrent_workers`, `thinker_cadence`).

### Backups and weekly reports (also reachable via cron/Task Scheduler)

```powershell
ros backup .\backups          # online SQLite snapshot + vault manifest
ros weekly-report              # writes vault/00_meta/WEEKLY.md
```

## 3. Connecting an AI coding agent

Research OS speaks plain **stdio MCP**, so the same server binary works
unchanged for Codex CLI, Cursor, and GitHub Copilot in VS Code. Config files
for all three are already checked into this repo — just open the project in
the tool of your choice and the server should be picked up automatically
(you may need to reload/restart the tool once).

| Tool | Config file | Notes |
|---|---|---|
| GitHub Copilot (VS Code) | [`.vscode/mcp.json`](../.vscode/mcp.json) | Uses `${workspaceFolder}`, works as-is. |
| Cursor | [`.cursor/mcp.json`](../.cursor/mcp.json) | Hardcodes the absolute repo path; edit it if you clone elsewhere. |
| Codex CLI | [`.codex/config.toml`](../.codex/config.toml) | Only loaded for projects you've marked as trusted. Alternative: `codex mcp add` (see comment in the file). |

All three configs point at `.venv\Scripts\python.exe -m research_os.mcp_server.server`
with `RESEARCH_OS_REPO` set to this repo, so make sure step 1 (`pip install -e
".[dev]"`) has been run in `.venv` before connecting.

### What role should the agent use?

Every MCP tool call takes a `role` and `run_id` argument; the ACL
(`configs/roles.yaml`) enforces what each role can do:

- **`human`** — unrestricted (`tools: all`). This is what you want when
  chatting interactively in Cursor/Copilot/Codex to explore the graph, pin
  nodes, resolve `NEEDS_HUMAN` reports, or trigger dispatch — tell your agent
  to pass `role="human"`.
- **`worker` / `reviewer` / `thinker` / `scheduler`** — the restricted,
  automated roles used internally by the scheduler/report pipeline. An
  interactive coding agent normally has no reason to impersonate these.

A good first prompt once connected: *"Using the research-os MCP tools with
role=human, show me the current frontier and activity dashboard."*

## 4. Testing

```powershell
pytest -q
ruff check src tests
```

## 5. Operational recovery

- **Projection/Git failed after accepted DB commit:** inspect
  `transactions.projection_status` and replay projection from the accepted
  transaction payload (`replay_projection` MCP tool).
- **Stale worker:** check `AGENT_ACTIVITY.md` Problems section and
  `agent_runs` / `agent_events` tables.
- **Rejected report:** see `vault/03_reports/` and `data/rejections/` for
  reason codes.
- **Disaster recovery:** restore the most recent `ros backup` snapshot with
  `ros restore <snapshot_dir>`.

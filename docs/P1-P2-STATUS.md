# Research OS — P1–P2 Status & Next Steps

_Last updated: 2026-08-06_

This document summarizes what was implemented through the P1–P2 plans and the follow-up **Close Remaining P1–P2 Gaps** work, and outlines sensible next steps.

---

## What was done

### P0 — Kernel (foundation)

- **Transaction kernel** with invariant enforcement and atomic SQLite commits before projection/Git.
- **Versioned migrations** (`schema_version`, currently **v6**).
- **Role-scoped MCP server** as the only mutation boundary for agents.
- **Obsidian vault projection** for knowledge graph nodes and frontier.
- **Git bridge** — one commit per accepted transaction (disabled in tests).

### P1 — Report intake & deterministic Reviewer

- **Immutable worker reports** stored in SQLite with normalized entities:
  - `report_claims`, `citations`, `candidate_operations`
  - `content_fingerprint` for deduplication
- **MCP tools**: `submit_report`, `get_report`, `list_pending_reports`, `review_report`
- **Anti-slop engine** with configurable gates (`configs/anti_slop.yaml`) and pluggable similarity backend.
- **Reviewer adjudication** with outcomes:
  - `ACCEPT`, `PARTIAL_ACCEPT`, `REJECT`, `NEEDS_HUMAN`
  - Claim-level accept/reject indices
  - Accepted claims compiled into invariant-enforced transactions
- **Report projections** under `vault/03_reports/` with evidence, citations, and review outcome.
- **Rejection artifacts** exported to `data/rejections/` when configured.

### P2 — Scheduler, Worker runtime, activity panel

- **Job/run/event/budget ledger** in SQLite with canonical lifecycle states.
- **Scheduler** (`dispatch_worker`) orchestrating worker → review pipeline.
- **Fake SDK worker** for offline CI (default path when `CURSOR_API_KEY` is absent).
- **Live Cursor SDK worker** (opt-in via `RESEARCH_OS_USE_LIVE_SDK=1` and `pip install -e ".[sdk]"`).
- **Isolated worker sandbox** with fail-closed Cursor hooks (shell/read/write denied; MCP-only).
- **Activity panel** at `vault/00_meta/AGENT_ACTIVITY.md` (gitignored, atomically written).

### Gap-closure hardening (latest pass)

#### Security & MCP boundary

- **Run-bound roles**: MCP rejects caller-supplied roles that don't match the authoritative role stored for `run_id`.
- **Worker sandbox whitelist**: Only `get_node`, `history`, `find_frontier`, `submit_report`, `consume_budget` allowed.
- **Typed MCP results**: Pydantic models for tool responses (`ApplyTransactionResult`, `CancelRunResult`, etc.).
- **`cancel_run` ACL** fixed to guard the correct tool.
- **Tests**: `tests/test_mcp_server.py` for role binding and ACL escalation rejection.

#### Report & review lifecycle

- **`NEEDS_HUMAN` report status** (distinct from `PENDING`).
- **Idempotent review** for recoverable states (`PENDING`, `IN_REVIEW`, `NEEDS_HUMAN`); duplicate decisions prevented.
- **Submit idempotency**: identical content returns existing report; different content from same run is rejected.
- **Schema**: stable claim `id` required; `proposed_objects` require `claim_index`.
- **Vault projection** reloads final SQLite state before writing frontmatter.

#### Migration v6

- Backfills **fingerprints** and **normalized report entities** from legacy v4/v5 databases.
- Rebuilds `agent_runs`, `jobs`, and `reports` with **CHECK constraints** on status/role values.
- Adds `sdk_agent_id`, `sdk_run_id`, `claim_id` columns.
- **Collision-safe run creation** (no `INSERT OR REPLACE` for runs).

#### Orchestration, budgets & live SDK

- **Attempt budget** enforced before dispatch.
- **Split failure handling**: worker failures vs reviewer failures update runs/jobs correctly.
- **Budget validation** with structured `BUDGET_EXHAUSTED` errors.
- **Cursor adapter**: SDK ID persistence, startup retries, sanitized heartbeats, no raw-output fallback.
- **Model resolver**: fails clearly when configured model isn't available (no silent substitution).
- **Cancellation** propagates to SDK via `run.cancel()` when supported.

#### Verification & delivery

- **38 tests passing**, 1 skipped (live SDK smoke test).
- **Ruff** clean.
- **GitHub Actions CI** (`.github/workflows/ci.yml`): install, pytest, ruff.
- **`requirements.lock`** regenerated; **Pydantic** declared as direct dependency.

### Key commits

| Commit   | Summary |
|----------|---------|
| `8bea784` | P0 kernel with SQLite, MCP, and tests |
| `49a24f5` | P1 report review loop and P2 scheduler/worker runtime |
| `858d8ed` | Normalized reports, lifecycle, typed MCP, verification |
| `1871229` | Gap closure: MCP security, lifecycle, migration v6, CI |
| `8278b71` | Follow-up (`p2`) |

---

## Can the system work now?

**Yes, for offline development and end-to-end fake-worker runs.**

```powershell
cd C:\!PROG\research-os
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

**Minimal smoke path:**

1. Admit a main conjecture via MCP (`apply_transaction` as reviewer/human).
2. Dispatch a worker: `dispatch_worker` (scheduler role) — uses fake SDK by default.
3. Reviewer adjudicates automatically; accepted knowledge appears in SQLite + Obsidian vault.
4. Check `vault/00_meta/AGENT_ACTIVITY.md` for the operational dashboard.

**Live Cursor SDK workers** require:

```powershell
pip install -e ".[sdk]"
$env:CURSOR_API_KEY = "your-key"
$env:RESEARCH_OS_USE_LIVE_SDK = "1"
pytest tests/test_live_sdk.py  # opt-in smoke test
```

---

## What to do next

### Immediate (operational)

1. **Run a real research session**
   - Open the Obsidian vault at `vault/`.
   - Admit your main conjecture.
   - Dispatch workers on frontier nodes and inspect report notes under `vault/03_reports/`.

2. **Push is synced** — `main` matches `origin/main`. CI should run on the next push/PR.

3. **Clean up local audit scratch files** (optional):
   - `_audit_*`, `_orig_plan.txt` in repo root are untracked temp artifacts; safe to delete.

### Short-term (P2 polish)

4. **Live SDK validation**
   - Run `tests/test_live_sdk.py` with a real `CURSOR_API_KEY`.
   - Confirm worker submits via MCP only (no fallback) and sandbox hooks block filesystem/shell.

5. **Human review workflow for `NEEDS_HUMAN`**
   - Reports escalated to `NEEDS_HUMAN` stay out of the auto-accept path.
   - Add an operator playbook: re-queue, edit directive, or manual `apply_transaction`.

6. **Budget tuning**
   - Adjust defaults in `configs/` and per-node budgets in SQLite.
   - Verify dispatch stops when attempt budget is exhausted.

7. **Obsidian workflow**
   - Link `HOME.md` → `AGENT_ACTIVITY.md` (already wired).
   - Use report notes and frontier panel as the daily research dashboard.

### Medium-term (P3+ — from README deferred list)

8. **Weighted frontier optimization** — replace simple ranking with configurable scoring.

9. **Thinker global passes** — periodic synthesis agent over the full graph (role exists in ACL; runtime not built).

10. **Embedding-backed semantic dedup** — replace token Jaccard similarity with embeddings in anti-slop.

11. **Custom Obsidian plugin** — richer live activity UI instead of markdown polling.

12. **Formal verification bridge** — Lean/Isabelle export (explicitly deferred in v0.1 decisions).

### Engineering debt / nice-to-haves

- **Migration fixtures**: add checked-in v4/v5 SQLite files for regression testing upgrades.
- **MCP integration tests**: call tools through FastMCP client, not just `_ctx`/`_guard` unit tests.
- **Reviewer retry**: scheduler could re-dispatch reviewer on transient failure instead of leaving job in `WAITING_FOR_REVIEW`.
- **Partial accept link scoping**: ensure `proposed_links` are tied to accepted claims when multiple claims exist.
- **README sync**: confirm Status section mentions v6 migration, role binding, and CI workflow.

---

## Quick reference

| Component | Location |
|-----------|----------|
| MCP server | `src/research_os/mcp_server/server.py` |
| Scheduler | `src/research_os/scheduler/service.py` |
| Reviewer | `src/research_os/reviewer/service.py` |
| Migrations | `src/research_os/store/migrations.py` (v6) |
| Roles ACL | `configs/roles.yaml` |
| Anti-slop | `configs/anti_slop.yaml` |
| Activity panel | `vault/00_meta/AGENT_ACTIVITY.md` |
| Architecture docs | `docs/architecture/README.md` |
| CI | `.github/workflows/ci.yml` |

---

## Suggested first session checklist

- [ ] `pytest` passes locally
- [ ] Admit one `MainConjecture` via MCP or test helper
- [ ] `dispatch_worker` on that node (fake SDK)
- [ ] Confirm new object in vault and graph stats increment
- [ ] Read `AGENT_ACTIVITY.md` in Obsidian
- [ ] (Optional) Run live SDK smoke test with API key
- [ ] Define your real main conjecture and first frontier targets

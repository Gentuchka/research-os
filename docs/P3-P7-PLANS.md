# Research OS — P3–P7 Implementation Plans

_Last updated: 2026-08-06_

This document defines the next five implementation phases after **P0–P2** (complete). Each phase builds on the prior one while preserving locked architecture decisions:

- **MCP-only mutation boundary**
- **SQLite canonical store** (until scale forces a migration decision)
- **Obsidian as human interface** (no web dashboard through P5)
- **Immutable knowledge + append-only history**
- **Goal = verified knowledge accumulation**, not “solve the conjecture”

See also: [P1–P2 Status](P1-P2-STATUS.md) · [Architecture](../architecture/README.md) · [ADRs](../decisions/)

---

## Roadmap overview

| Phase | Theme | Outcome |
|-------|-------|---------|
| **P3** | Operator control & Thinker | Human can steer research; Thinker runs globally; frontier becomes trustworthy |
| **P4** | Graph intelligence & search | Navigate and deduplicate a growing graph; auto-supersede; node lifecycle |
| **P5** | Obsidian experience | Readable long-term UI without hand-editing generated notes |
| **P6** | Formal verification bridge | Export and track formal proofs; optional external checker hooks |
| **P7** | Longevity & scale | Months/years of unattended operation; backup, analytics, optional multi-repo |

**Dependency chain:** P3 → P4 → P5 can overlap slightly; P6 depends on stable object schemas (P4); P7 depends on operational maturity (P3–P5).

---

## P3 — Operator control, Thinker, and frontier maturity

**Goal:** Turn the P2 loop into a **steerable research program** a human can run for weeks. Close the gap between “demo works” and “I trust dispatch decisions.”

### Prerequisites (from P2)

- [x] Worker → report → reviewer → transaction loop
- [x] Job/run/budget ledger
- [x] Activity panel
- [x] Role-bound MCP + worker sandbox

### Scope

#### 3.1 Human operator MCP tools

Implement the actions promised in [ADR 003](../decisions/003-obsidian-only-ui.md) and `vault/00_meta/HOME.md`:

| Tool | Purpose |
|------|---------|
| `pin_node` | Boost frontier rank; record human priority |
| `freeze_node` | Remove from frontier until unfrozen |
| `inject_literature` | Admit `Paper` objects with bibliographic metadata |
| `override_budget` | Set per-node attempt/token/tool budgets |
| `dispatch_thinker` | Queue a Thinker run (global synthesis) |
| `resolve_needs_human` | Re-queue or close escalated reports |

All tools use role=`human`, append audit events, and never bypass invariants.

#### 3.2 Thinker agent runtime

- **Thinker role** already exists in `configs/roles.yaml` and `configs/models.yaml`; build the runtime mirroring Worker:
  - Cursor SDK adapter (live) + fake adapter (CI)
  - Sandbox: read-heavy MCP whitelist (`graph_statistics`, `find_frontier`, `history`, `get_node`, `submit_report`)
  - **Thinker reports** use `report_type: thinker` with strategic claims (new conjectures, technique suggestions, missing links) — no local node investigation
- **Scheduler integration:** `dispatch_thinker` on cadence (configurable) or manual trigger; separate job type from worker jobs
- **Reviewer path:** Thinker reports go through same anti-slop + adjudication pipeline

#### 3.3 Frontier scoring v2

Current state: `configs/frontier.yaml` weights exist; many metrics are defaulted to `0.5` because they are not computed.

Deliver:

- **Metric pipeline** that populates `importance`, `promise`, `novelty`, `information_gain`, `research_cost`, `verification_confidence` on admit/review
- **Human pin tie-breaker** from `pin_node`
- **Budget-aware cost term** (nodes near exhaustion rank lower)
- **Frontier projection v2** — ranked table with scores and rationale in `vault/04_frontier/current.md`
- **Scheduler** uses ranked frontier by default; respects `freeze_node`

#### 3.4 Embedding-backed anti-slop

Replace or augment `TokenJaccardSimilarity` with an embedding backend:

- Pluggable `SimilarityBackend` (already exists)
- Local or API embedding provider (config-driven)
- Thresholds in `configs/anti_slop.yaml` for near-duplicate claims and cosmetic variants
- Offline tests with fixed embedding fixtures

#### 3.5 NEEDS_HUMAN operator workflow

- MCP tool + vault note banner for escalated reports
- Re-submission path after human edits directive
- Activity panel section: “Awaiting human decision”

### Key files to touch

- `src/research_os/mcp_server/server.py` — new human tools
- `src/research_os/agents/thinker/` — new package
- `src/research_os/scheduler/service.py` — thinker dispatch, frontier v2
- `src/research_os/metrics/engine.py` — full metric computation
- `src/research_os/anti_slop/similarity.py` — embedding backend
- `configs/frontier.yaml`, `configs/anti_slop.yaml`
- `schemas/reports.schema.json` — thinker report variants if needed

### Success criteria

- [ ] Human can pin, freeze, and inject a Paper without editing SQLite or vault by hand
- [ ] Thinker fake run produces a report; reviewer accepts/rejects deterministically
- [ ] Frontier ranking changes measurably when pin/freeze/budget applied
- [ ] Embedding dedup catches paraphrased duplicate claim in test fixture
- [ ] NEEDS_HUMAN report visible in activity panel with operator action

### Estimated effort

**Medium** — 2–3 focused implementation passes.

---

## P4 — Graph intelligence, search, and node lifecycle

**Goal:** Keep the knowledge graph **navigable and clean** as it grows to hundreds/thousands of nodes.

### Scope

#### 4.1 MCP read/search tools

Implement high-value read tools from the original spec (read-only, no graph mutation):

| Tool | Purpose |
|------|---------|
| `semantic_search` | Embedding query over statements/titles |
| `find_similar` | Near-duplicates for a given node |
| `find_orphans` | Nodes with no math edges |
| `find_dead_nodes` | STUCK/FROZEN/ARCHIVED with no recent activity |
| `timeline` | Event stream across graph or node |
| `nearest_main` | Shortest path to main conjecture |
| `search_by_definition` | Definition-linked objects |
| `search_counterexamples` | Counterexamples by target |
| `search_techniques` | Technique objects and usages |

All return structured JSON; vault projections optionally mirror summaries.

#### 4.2 Automatic superseding

From original spec: stronger counterexample should supersede weaker hypotheses.

- Reviewer rule extension: on `Counterexample` admit, traverse `disproved_by` / `kills` edges
- Mark weaker active hypotheses `SUPERSEDED` in same transaction batch
- Provenance records why supersession occurred
- Tests: one counterexample → multiple hypotheses superseded

#### 4.3 Node lifecycle: STUCK / FROZEN

Budget exhaustion currently blocks dispatch; extend with explicit statuses:

- **`STUCK`** — attempt budget exhausted, no new evidence
- **`FROZEN`** — human or Thinker freeze; excluded from frontier
- **`ARCHIVED`** — already supported; wire to dead-end workflow

Scheduler skips STUCK/FROZEN nodes; activity panel shows why.

#### 4.4 Equivalence class operations

Per [ADR 002](../decisions/002-equivalence-classes.md):

- Reviewer-initiated `MergeEquivalenceClassOp` from duplicate detection
- Frontier/metrics always use class representative
- Vault shows class membership in provenance section

#### 4.5 Optional Reviewer LLM assist

`configs/models.yaml` already has `reviewer.llm.enabled`. Behind a flag:

- LLM reads report + graph context for **advisory** flags only
- Deterministic anti-slop remains authoritative
- LLM output stored as `agent_events`, never auto-writes graph

### Key files to touch

- `src/research_os/mcp_server/server.py`
- `src/research_os/reviewer/service.py`
- `src/research_os/kernel/invariants.py`
- `src/research_os/store/repository.py` — search indexes (FTS5 or embedding table)
- `src/research_os/projection/vault.py` — timeline, orphan views

### Success criteria

- [ ] `semantic_search` returns relevant nodes in integration test
- [ ] Counterexample admission supersedes ≥2 weaker hypotheses in fixture graph
- [ ] STUCK node excluded from `dispatch_worker` with clear reason
- [ ] Duplicate hypotheses merged into equivalence class without DAG cycle
- [ ] Reviewer LLM assist off by default; on flag adds non-blocking findings

### Estimated effort

**Medium–large** — search indexing and superseding logic need careful invariant tests.

---

## P5 — Obsidian experience and operator UX

**Goal:** Make the vault **pleasant for daily reading** over months; reduce reliance on raw MCP JSON for operators.

**Constraint:** [ADR 003](../decisions/003-obsidian-only-ui.md) — no web dashboard through P5. Enhance Obsidian, not replace it.

### Scope

#### 5.1 Custom Obsidian plugin (`research-os-obsidian`)

- Live **Agent Activity** panel (poll or file-watch `AGENT_ACTIVITY.md`)
- **Frontier widget** — top N nodes with scores, pin/freeze indicators
- **Report inbox** — pending / NEEDS_HUMAN with one-click “open in note”
- **Graph stats** sidebar (object counts, recent admits)
- Plugin reads vault only; **writes go through MCP** (plugin calls local operator script or MCP bridge)

#### 5.2 Enhanced vault projections

- `vault/00_meta/STATISTICS.md` — auto-generated dashboard
- `vault/00_meta/TIMELINE.md` — rolling research timeline
- `vault/05_dead_ends/` — structured dead-end summaries
- Per-node **report history** section (links to `03_reports/`)
- Diff-friendly report rejection notes

#### 5.3 Operator CLI (`research-os` or `ros`)

Thin wrapper over MCP for humans:

```powershell
ros pin ros_hyp_...
ros dispatch worker --node ros_hyp_...
ros dispatch thinker
ros activity
ros resolve-report ros_rpt_... --accept
```

Same ACL as role=`human`; no direct DB access.

#### 5.4 Activity panel v2

- Prose summaries per run (not just status strings)
- “What changed in the graph” after each accepted transaction
- Separate sections: working / waiting / needs human / failed / stale
- Link to accepted objects and report notes

### Key files to touch

- New: `obsidian-plugin/` (TypeScript)
- New: `src/research_os/cli/` or `scripts/ros.py`
- `src/research_os/projection/activity.py`, `vault.py`
- `vault/00_meta/HOME.md` — navigation updates

### Success criteria

- [ ] Plugin installs in Obsidian and shows live activity without manual refresh
- [ ] Operator can pin + dispatch from CLI without editing JSON
- [ ] STATISTICS and TIMELINE pages regenerate on accepted transaction
- [ ] Human never needs to read SQLite or raw MCP responses for daily ops

### Estimated effort

**Medium** — plugin is new surface area; CLI is thin if MCP is stable.

---

## P6 — Formal verification bridge

**Goal:** Connect informal graph knowledge to **machine-checkable artifacts** without making Lean/Isabelle the source of truth.

Per [ADR 006](../decisions/006-no-formal-verification-yet.md): no prover in the kernel; export and track only.

### Scope

#### 6.1 Proof artifact model

- Extend `Proof` objects with:
  - `formalization` field (already in schema)
  - `prover` enum: `lean4`, `isabelle`, `manual`, `none`
  - `artifact_uri` — path or URL to checked-in proof file
  - `verification_status`: `UNVERIFIED`, `CHECKING`, `VERIFIED`, `FAILED`

#### 6.2 Export pipeline

- `export_formal` MCP tool (human/reviewer): emit Lean/Isabelle skeleton from Definition/Lemma/Proof nodes
- Git tracks exported files under `formal/` (optional directory)
- Export is **derived**; canonical store remains SQLite

#### 6.3 External verifier hooks

- Subprocess runner for `lean` / `isabelle build` (opt-in, CI-gated)
- Results → `verification_status` + `agent_events`
- Failed verification does **not** auto-delete Proof; marks status FAILED with log

#### 6.4 Reviewer integration

- Anti-slop gate: claims of “formally proved” require `verification_status=VERIFIED`
- Reviewer can admit Proof with `UNVERIFIED` + human acknowledgment

### Key files to touch

- `schemas/objects.schema.json` — proof fields
- New: `src/research_os/formal/export.py`, `verify.py`
- `src/research_os/mcp_server/server.py`
- `formal/` directory layout + templates

### Success criteria

- [ ] Export Lemma to Lean stub from MCP
- [ ] Manual proof file + hook marks object VERIFIED in test
- [ ] Reviewer rejects “proved in Lean” claim when status is UNVERIFIED
- [ ] No prover code in transaction hot path

### Estimated effort

**Medium** — mostly boundaries and tooling; full formal library is out of scope.

---

## P7 — Longevity, scale, and unattended operation

**Goal:** Run Research OS **continuously for months** with confidence in data durability and operational visibility.

### Scope

#### 7.1 Scheduler daemon

- Long-running `research-os-scheduler` process:
  - Poll frontier on interval
  - Respect global concurrency limits (max N workers)
  - Periodic Thinker cadence from config
  - Graceful shutdown + run cancellation
- Systemd / Windows Service docs (not mandatory implementation)

#### 7.2 Backup and recovery

- `research-os backup` — SQLite snapshot + vault rsync manifest
- `research-os restore` — verified restore procedure
- Document projection replay + Git reconciliation playbook
- Optional: export canonical graph to portable JSONL archive

#### 7.3 Analytics and research health

- Weekly auto-report: nodes admitted, reject rate, budget burn, frontier movement
- Slop rejection breakdown by reason code
- “Research velocity” metrics (accepted information per run)
- Projected to `vault/00_meta/WEEKLY.md`

#### 7.4 Scale options (evaluate, not necessarily implement)

- SQLite → PostgreSQL migration path if graph exceeds ~500k objects
- Embedding index external store (sqlite-vec, pgvector)
- Multi-conjecture / multi-project: separate DB per program or tenant prefix

#### 7.5 Hardening pass

- Property-based tests on invariant engine
- Chaos tests: kill worker mid-run, verify ledger consistency
- Load test: 1000 report submissions, migration upgrade from v6

### Key files to touch

- New: `src/research_os/daemon/scheduler_daemon.py`
- New: `src/research_os/backup/`
- `src/research_os/store/migrations.py` — v7+ only if needed
- `docs/operations/` — runbooks

### Success criteria

- [ ] Daemon runs 24h test with fake workers without ledger corruption
- [ ] Backup → restore → identical graph statistics
- [ ] Weekly report generates with accurate reject/slop stats
- [ ] Documented recovery from projection failure + Git mismatch

### Estimated effort

**Large** — daemon and backup are ops-critical; scale migration is exploratory.

---

## Cross-phase engineering standards

Every phase should include:

1. **Schema migration** — forward-only, tested from previous version
2. **MCP typed models** — Pydantic request/response for new tools
3. **ACL updates** — `configs/roles.yaml` deny lists stay minimal
4. **Offline tests** — fake SDK / fixtures; live tests opt-in
5. **Projection updates** — vault reflects new state; no hand-editing
6. **ADR** — any locked decision change gets a new `docs/decisions/` entry

---

## Suggested implementation order (within P3–P7)

```
P3.1 Human MCP tools          ─┐
P3.2 Frontier metrics v2      ─┼─► usable steering
P3.5 NEEDS_HUMAN workflow     ─┘

P3.3 Thinker runtime          ─┐
P3.4 Embedding anti-slop      ─┼─► strategic + quality layer

P4.1 Search MCP tools         ─┐
P4.2 Auto-superseding         ─┼─► graph stays clean at scale
P4.3 STUCK/FROZEN lifecycle   ─┘

P5.3 Operator CLI             ─┐
P5.2 Enhanced projections     ─┼─► daily human UX
P5.1 Obsidian plugin          ─┘

P6.1–6.3 Formal export/verify  ─► optional proof track

P7.1 Scheduler daemon          ─┐
P7.2 Backup/recovery          ─┼─► months-long operation
P7.3 Analytics                ─┘
```

---

## What to implement first (recommended)

If you want **maximum value per week** after P2:

1. **P3.1 + P3.2** — pin/freeze/literature + real frontier metrics (you can steer dispatch)
2. **P3.5** — NEEDS_HUMAN workflow (unblocks escalated reports)
3. **P3.3** — Thinker fake runtime (strategic reports without live SDK)
4. **P5.3** — operator CLI (ergonomic daily use)
5. **P4.2** — auto-superseding (graph hygiene)

Defer **P6** until you have real proofs worth exporting. Defer **P7 daemon** until you run unattended overnight.

---

## Open decisions (resolve before P5+)

| Question | Options | Recommendation |
|----------|---------|----------------|
| Embedding provider | Local model vs API | Local for privacy; API behind config flag |
| Obsidian plugin scope | Read-only vs MCP bridge | MCP bridge for pin/dispatch |
| Reviewer LLM | Off / advisory / blocking | Advisory only, off by default |
| Formal directory | In-repo `formal/` vs submodule | In-repo for v0.1 |
| Scale store | Stay SQLite vs PostgreSQL | SQLite through P7 unless >100k nodes |

---

## Related documents

- [P1–P2 Status & Next Steps](P1-P2-STATUS.md)
- [Architecture overview](../architecture/README.md)
- [ADR 003: Obsidian-only UI](../decisions/003-obsidian-only-ui.md)
- [ADR 006: No formal verification yet](../decisions/006-no-formal-verification-yet.md)
- Original project spec (agent transcript): Research OS Technical Specification v0.1

"""Repository for knowledge graph persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from research_os.kernel.types import (
    AppendMetricOp,
    AppendNodeOp,
    ArchiveNodeOp,
    CreateLinkOp,
    InvariantCode,
    KernelError,
    MergeEquivalenceClassOp,
    Operation,
    Provenance,
    ResearchObject,
    SetStatusOp,
    SupersedeNodeOp,
    canonical_content_hash,
    utc_now,
)
from research_os.reports.types import ReportStatus, ResearchReport, ReviewDecision
from research_os.store.run_lifecycle import (
    ACTIVE_RUN_STATUSES,
    ALLOWED_BUDGET_NAMES,
    LEGAL_JOB_TRANSITIONS,
    LEGAL_RUN_TRANSITIONS,
    TERMINAL_RUN_STATUSES,
    RunStatus,
    assert_legal_transition,
)


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_object(self, node_id: str) -> ResearchObject | None:
        row = self.conn.execute("SELECT * FROM objects WHERE id = ?", (node_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_object(row)

    def object_exists(self, node_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM objects WHERE id = ?", (node_id,)).fetchone()
        return row is not None

    def content_hash_exists(self, content_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM objects WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return row is not None

    def list_objects(self, *, status: str | None = None, limit: int = 100) -> list[ResearchObject]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM objects WHERE status = ? ORDER BY created_at LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM objects ORDER BY created_at LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_object(row) for row in rows]

    def list_math_edges(self) -> list[tuple[str, str, str]]:
        rows = self.conn.execute("SELECT from_id, to_id, edge_type FROM math_edges").fetchall()
        return [(row["from_id"], row["to_id"], row["edge_type"]) for row in rows]

    def list_provenance_edges(self) -> list[tuple[str, str, str]]:
        rows = self.conn.execute(
            "SELECT from_id, to_id, edge_type FROM provenance_edges"
        ).fetchall()
        return [(row["from_id"], row["to_id"], row["edge_type"]) for row in rows]

    def get_frontier(self, limit: int = 20) -> list[ResearchObject]:
        rows = self.conn.execute(
            """
            SELECT * FROM objects
            WHERE status = 'ACTIVE' AND is_class_representative = 1
            ORDER BY created_at
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_object(row) for row in rows]

    def get_events_for_node(self, node_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT event_type, payload_json, created_at, transaction_id
            FROM events
            WHERE node_id = ?
            ORDER BY id
            """,
            (node_id,),
        ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
                "transaction_id": row["transaction_id"],
            }
            for row in rows
        ]

    def apply_ops(self, tx_id: str, ops: list[Operation]) -> list[str]:
        affected: list[str] = []
        now = utc_now().isoformat()
        for op in ops:
            if isinstance(op, AppendNodeOp):
                self._append_node(tx_id, op, now)
                affected.append(op.object.id)
            elif isinstance(op, ArchiveNodeOp):
                self._archive_node(tx_id, op, now)
                affected.append(op.node_id)
            elif isinstance(op, SupersedeNodeOp):
                self._supersede_node(tx_id, op, now)
                affected.extend([op.old_id, op.new_id])
            elif isinstance(op, CreateLinkOp):
                self._create_link(tx_id, op, now)
                affected.extend([op.from_id, op.to_id])
            elif isinstance(op, MergeEquivalenceClassOp):
                self._merge_equivalence(tx_id, op, now)
                affected.extend([op.representative_id, op.member_id])
            elif isinstance(op, SetStatusOp):
                self._set_status(tx_id, op, now)
                affected.append(op.node_id)
            elif isinstance(op, AppendMetricOp):
                self._append_metric(tx_id, op, now)
                affected.append(op.node_id)
            else:
                raise ValueError(f"Unknown operation: {op}")
        return list(dict.fromkeys(affected))

    def record_transaction(
        self,
        tx_id: str,
        actor_role: str,
        actor_run_id: str,
        summary: str,
        accepted: bool,
        payload: dict[str, Any],
        git_commit_sha: str | None = None,
        projection_status: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO transactions(
                id, actor_role, actor_run_id, summary, created_at,
                accepted, git_commit_sha, projection_status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tx_id,
                actor_role,
                actor_run_id,
                summary,
                utc_now().isoformat(),
                1 if accepted else 0,
                git_commit_sha,
                projection_status,
                json.dumps(payload),
            ),
        )

    def update_transaction_projection(self, tx_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE transactions SET projection_status = ? WHERE id = ?",
            (status, tx_id),
        )

    def _append_node(self, tx_id: str, op: AppendNodeOp, now: str) -> None:
        obj = op.object
        admitted_at = obj.admitted_at or now
        self.conn.execute(
            """
            INSERT INTO objects(
                id, type, title, statement, formalization, status, created_at,
                admitted_at, content_hash, equivalence_class_id,
                is_class_representative, provenance_json, evidence_refs_json,
                tags_json, information_gain
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obj.id,
                obj.type,
                obj.title,
                obj.statement,
                obj.formalization,
                obj.status,
                obj.created_at,
                admitted_at,
                obj.content_hash,
                obj.equivalence_class_id,
                1 if obj.is_class_representative else 0,
                json.dumps(obj.provenance.to_dict()),
                json.dumps(obj.evidence_refs),
                json.dumps(obj.tags),
                obj.information_gain,
            ),
        )
        self.conn.execute(
            """
            INSERT INTO object_versions(
                object_id, content_hash, payload_json, admitted_at, transaction_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                obj.id,
                obj.content_hash,
                json.dumps(obj.content_payload()),
                admitted_at,
                tx_id,
            ),
        )
        self.conn.execute(
            """
            INSERT INTO budgets(
                node_id, attempt_budget, token_budget, time_budget_seconds,
                tool_budget, branch_budget
            ) VALUES (?, 8, 200000, 3600, 50, 3)
            """,
            (obj.id,),
        )
        self._record_event(
            tx_id,
            "NODE_ADMITTED",
            {"node_id": obj.id, "type": obj.type, "status": obj.status},
            now,
            node_id=obj.id,
        )

    def _archive_node(self, tx_id: str, op: ArchiveNodeOp, now: str) -> None:
        self.conn.execute(
            "UPDATE objects SET status = 'ARCHIVED' WHERE id = ?",
            (op.node_id,),
        )
        self._record_event(
            tx_id,
            "NODE_ARCHIVED",
            {"node_id": op.node_id, "reason": op.reason},
            now,
        )

    def _supersede_node(self, tx_id: str, op: SupersedeNodeOp, now: str) -> None:
        self.conn.execute(
            "UPDATE objects SET status = 'SUPERSEDED' WHERE id = ?",
            (op.old_id,),
        )
        self.conn.execute(
            """
            INSERT INTO math_edges(from_id, to_id, edge_type, created_at, transaction_id)
            VALUES (?, ?, 'supersedes', ?, ?)
            """,
            (op.new_id, op.old_id, now, tx_id),
        )
        self._record_event(
            tx_id,
            "NODE_SUPERSEDED",
            {"old_id": op.old_id, "new_id": op.new_id, "reason": op.reason},
            now,
        )

    def _create_link(self, tx_id: str, op: CreateLinkOp, now: str) -> None:
        table = "math_edges" if op.graph == "math" else "provenance_edges"
        self.conn.execute(
            f"""
            INSERT INTO {table}(from_id, to_id, edge_type, created_at, transaction_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (op.from_id, op.to_id, op.edge_type, now, tx_id),
        )
        self._record_event(
            tx_id,
            "LINK_CREATED",
            {
                "from_id": op.from_id,
                "to_id": op.to_id,
                "edge_type": op.edge_type,
                "graph": op.graph,
            },
            now,
        )

    def _merge_equivalence(self, tx_id: str, op: MergeEquivalenceClassOp, now: str) -> None:
        rep = self.get_object(op.representative_id)
        if rep is None:
            raise ValueError(f"Representative not found: {op.representative_id}")
        class_id = op.class_id or rep.equivalence_class_id or f"ros_eq_{op.representative_id}"
        if not self.conn.execute(
            "SELECT 1 FROM equivalence_classes WHERE id = ?", (class_id,)
        ).fetchone():
            self.conn.execute(
                """
                INSERT INTO equivalence_classes(id, representative_id, created_at, transaction_id)
                VALUES (?, ?, ?, ?)
                """,
                (class_id, op.representative_id, now, tx_id),
            )
        self.conn.execute(
            """
            UPDATE objects
            SET equivalence_class_id = ?, is_class_representative = 1
            WHERE id = ?
            """,
            (class_id, op.representative_id),
        )
        self.conn.execute(
            """
            UPDATE objects
            SET equivalence_class_id = ?, is_class_representative = 0, status = 'SUPERSEDED'
            WHERE id = ?
            """,
            (class_id, op.member_id),
        )
        self.conn.execute(
            """
            INSERT INTO provenance_edges(from_id, to_id, edge_type, created_at, transaction_id)
            VALUES (?, ?, 'prov:member_of_class', ?, ?)
            """,
            (op.member_id, class_id, now, tx_id),
        )
        self._record_event(
            tx_id,
            "EQUIVALENCE_MERGED",
            {
                "class_id": class_id,
                "representative_id": op.representative_id,
                "member_id": op.member_id,
            },
            now,
        )

    def _set_status(self, tx_id: str, op: SetStatusOp, now: str) -> None:
        self.conn.execute(
            "UPDATE objects SET status = ?, evidence_refs_json = ? WHERE id = ?",
            (op.status, json.dumps(op.evidence_refs), op.node_id),
        )
        self._record_event(
            tx_id,
            "STATUS_CHANGED",
            {
                "node_id": op.node_id,
                "status": op.status,
                "evidence_refs": op.evidence_refs,
                "reason": op.reason,
            },
            now,
        )

    def _append_metric(self, tx_id: str, op: AppendMetricOp, now: str) -> None:
        self.conn.execute(
            """
            INSERT INTO metrics(
                node_id, metric_name, value, method, version, created_at, transaction_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (op.node_id, op.metric_name, op.value, op.method, op.version, now, tx_id),
        )
        self._record_event(
            tx_id,
            "METRIC_UPDATED",
            {
                "node_id": op.node_id,
                "metric_name": op.metric_name,
                "value": op.value,
            },
            now,
        )

    def _record_event(
        self,
        tx_id: str,
        event_type: str,
        payload: dict[str, Any],
        now: str,
        node_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO events(
                event_type, payload_json, created_at, transaction_id, node_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (event_type, json.dumps(payload), now, tx_id, node_id or payload.get("node_id")),
        )

    def literature_exists(self, ref: str) -> bool:
        if ref.startswith("bootstrap") or ref.startswith("ros_"):
            return self.object_exists(ref)
        return ref in self._known_literature()

    def _known_literature(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT id FROM objects WHERE type = 'Paper'"
        ).fetchall()
        return {row["id"] for row in rows}

    def save_report(self, report: ResearchReport) -> None:
        fingerprint = self._report_fingerprint(report.payload)
        self.conn.execute(
            """
            INSERT INTO reports(
                id, report_type, subject_node_id, status, run_id, payload_json,
                created_at, content_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.id,
                report.report_type,
                report.subject_node_id,
                report.status,
                report.run_id,
                json.dumps(report.payload),
                report.created_at,
                fingerprint,
            ),
        )
        self.save_report_entities(report)

    def save_report_entities(self, report: ResearchReport) -> None:
        now = utc_now().isoformat()
        payload = report.payload
        for idx, claim in enumerate(payload.get("claims", [])):
            self.conn.execute(
                """
                INSERT INTO report_claims(
                    report_id, claim_index, claim_id, text, speculative,
                    evidence_refs_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    idx,
                    claim.get("id", f"claim_{idx}"),
                    claim.get("text", ""),
                    int(bool(claim.get("speculative"))),
                    json.dumps(claim.get("evidence_refs", [])),
                    now,
                ),
            )
        for ref in payload.get("literature_refs", []):
            self.conn.execute(
                "INSERT INTO citations(report_id, ref, created_at) VALUES (?, ?, ?)",
                (report.id, ref, now),
            )
        op_index = 0
        for proposed in payload.get("proposed_objects", []):
            self.conn.execute(
                """
                INSERT INTO candidate_operations(
                    report_id, op_index, op_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    op_index,
                    "append_node",
                    json.dumps(proposed),
                    now,
                ),
            )
            op_index += 1
        for link in payload.get("proposed_links", []):
            self.conn.execute(
                """
                INSERT INTO candidate_operations(
                    report_id, op_index, op_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    op_index,
                    "create_link",
                    json.dumps(link),
                    now,
                ),
            )
            op_index += 1

    def get_report_by_fingerprint(self, fingerprint: str) -> ResearchReport | None:
        row = self.conn.execute(
            "SELECT * FROM reports WHERE content_fingerprint = ? ORDER BY created_at DESC LIMIT 1",
            (fingerprint,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_report(row)

    def has_review_decision(self, report_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM review_decisions WHERE report_id = ? LIMIT 1",
            (report_id,),
        ).fetchone()
        return row is not None

    def get_latest_decision(self, report_id: str) -> ReviewDecision | None:
        row = self.conn.execute(
            """
            SELECT * FROM review_decisions
            WHERE report_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_decision(row)

    def close_review_queue(self, report_id: str, reviewer_run_id: str) -> None:
        self.conn.execute(
            """
            UPDATE review_queue
            SET status = 'decided', reviewer_run_id = ?, decided_at = ?
            WHERE report_id = ? AND status = 'pending'
            """,
            (reviewer_run_id, utc_now().isoformat(), report_id),
        )

    def _report_fingerprint(self, payload: dict[str, Any]) -> str:
        normalized = {
            "subject_node_id": payload["subject_node_id"],
            "information_delta": sorted(payload.get("information_delta", [])),
            "claims": [c.get("text", "") for c in payload.get("claims", [])],
        }
        return canonical_content_hash(normalized)

    def _row_to_report(self, row: sqlite3.Row) -> ResearchReport:
        return ResearchReport(
            id=row["id"],
            report_type=row["report_type"],
            subject_node_id=row["subject_node_id"],
            status=row["status"],
            run_id=row["run_id"],
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
        )

    def _row_to_decision(self, row: sqlite3.Row) -> ReviewDecision:
        keys = row.keys()
        return ReviewDecision(
            id=row["id"],
            report_id=row["report_id"],
            decision=row["decision"],
            reason_codes=json.loads(row["reason_codes_json"]),
            reviewer_run_id=row["reviewer_run_id"],
            transaction_id=row["transaction_id"],
            created_at=row["created_at"],
            accepted_claim_indices=json.loads(row["accepted_claim_indices_json"])
            if "accepted_claim_indices_json" in keys and row["accepted_claim_indices_json"]
            else [],
            rejected_claim_indices=json.loads(row["rejected_claim_indices_json"])
            if "rejected_claim_indices_json" in keys and row["rejected_claim_indices_json"]
            else [],
        )

    def get_report_claims(self, report_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT claim_index, claim_id, text, speculative, evidence_refs_json
            FROM report_claims
            WHERE report_id = ?
            ORDER BY claim_index
            """,
            (report_id,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            keys = row.keys()
            result.append(
                {
                    "claim_index": row["claim_index"],
                    "id": row["claim_id"] if "claim_id" in keys and row["claim_id"] else None,
                    "text": row["text"],
                    "speculative": bool(row["speculative"]),
                    "evidence_refs": json.loads(row["evidence_refs_json"]),
                }
            )
        return result

    def get_report_citations(self, report_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT ref FROM citations WHERE report_id = ? ORDER BY id",
            (report_id,),
        ).fetchall()
        return [row["ref"] for row in rows]

    def get_candidate_operations(self, report_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT op_index, op_type, payload_json
            FROM candidate_operations
            WHERE report_id = ?
            ORDER BY op_index
            """,
            (report_id,),
        ).fetchall()
        return [
            {
                "op_index": row["op_index"],
                "op_type": row["op_type"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        return None if row is None else dict(row)

    def get_run_role(self, run_id: str) -> str | None:
        row = self.conn.execute("SELECT role FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        return None if row is None else row["role"]

    def persist_sdk_ids(self, run_id: str, sdk_agent_id: str, sdk_run_id: str) -> None:
        self.conn.execute(
            """
            UPDATE agent_runs
            SET sdk_agent_id = ?, sdk_run_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (sdk_agent_id, sdk_run_id, utc_now().isoformat(), run_id),
        )

    def get_sdk_run_id(self, run_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT sdk_run_id FROM agent_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        keys = row.keys()
        return row["sdk_run_id"] if "sdk_run_id" in keys else None

    def has_attempt_budget(self, node_id: str) -> bool:
        row = self.conn.execute(
            "SELECT attempt_budget, attempt_used FROM budgets WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            return True
        return float(row["attempt_used"]) < float(row["attempt_budget"])

    def get_report(self, report_id: str) -> ResearchReport | None:
        row = self.conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_report(row)

    def list_reports_for_node(self, node_id: str) -> list[ResearchReport]:
        rows = self.conn.execute(
            "SELECT * FROM reports WHERE subject_node_id = ? ORDER BY created_at",
            (node_id,),
        ).fetchall()
        return [
            self._row_to_report(row)
            for row in rows
        ]

    def list_pending_reports(self) -> list[ResearchReport]:
        rows = self.conn.execute(
            "SELECT * FROM reports WHERE status = ? ORDER BY created_at",
            (ReportStatus.PENDING.value,),
        ).fetchall()
        return [self._row_to_report(row) for row in rows]

    def update_report_status(self, report_id: str, status: str) -> None:
        self.conn.execute("UPDATE reports SET status = ? WHERE id = ?", (status, report_id))

    def enqueue_review(self, report_id: str, worker_run_id: str) -> None:
        from ulid import ULID

        self.conn.execute(
            """
            INSERT INTO review_queue(
                id, report_id, worker_run_id, reviewer_run_id, status, enqueued_at, decided_at
            ) VALUES (?, ?, ?, NULL, 'pending', ?, NULL)
            """,
            (f"ros_rq_{ULID()}", report_id, worker_run_id, utc_now().isoformat()),
        )

    def save_review_decision(self, decision: ReviewDecision) -> None:
        self.conn.execute(
            """
            INSERT INTO review_decisions(
                id, report_id, decision, reason_codes_json, reviewer_run_id,
                transaction_id, created_at, accepted_claim_indices_json,
                rejected_claim_indices_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.id,
                decision.report_id,
                decision.decision,
                json.dumps(decision.reason_codes),
                decision.reviewer_run_id,
                decision.transaction_id,
                decision.created_at,
                json.dumps(decision.accepted_claim_indices),
                json.dumps(decision.rejected_claim_indices),
            ),
        )

    def list_review_queue(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM review_queue WHERE status = 'pending' ORDER BY enqueued_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def create_job(self, job_id: str, node_id: str, *, priority: float = 0.0) -> None:
        now = utc_now().isoformat()
        self.conn.execute(
            """
            INSERT INTO jobs(id, node_id, status, priority, assigned_run_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, NULL, ?, ?)
            """,
            (job_id, node_id, RunStatus.QUEUED.value, priority, now, now),
        )

    def update_job_status(
        self,
        job_id: str,
        status: str,
        *,
        assigned_run_id: str | None = None,
    ) -> None:
        row = self.conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError(f"Job not found: {job_id}")
        assert_legal_transition(row["status"], status, LEGAL_JOB_TRANSITIONS, label="job")
        now = utc_now().isoformat()
        self.conn.execute(
            """
            UPDATE jobs
            SET status = ?, assigned_run_id = COALESCE(?, assigned_run_id), updated_at = ?
            WHERE id = ?
            """,
            (status, assigned_run_id, now, job_id),
        )

    def list_waiting_jobs(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM jobs
            WHERE status IN ('WAITING_FOR_REVIEW', 'QUEUED')
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_blocked_jobs(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM jobs
            WHERE status IN ('FAILED', 'CANCELLED')
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def consume_node_budget(self, node_id: str, budget_name: str, amount: float) -> float:
        if budget_name not in ALLOWED_BUDGET_NAMES:
            raise KernelError(
                InvariantCode.BUDGET_EXHAUSTED,
                f"Unknown budget name: {budget_name}",
            )
        defaults = {
            "attempt": "attempt_budget",
            "token": "token_budget",
            "time": "time_budget_seconds",
            "tool": "tool_budget",
            "branch": "branch_budget",
        }
        column = defaults.get(budget_name, f"{budget_name}_budget")
        used_column = column.replace("_budget", "_used").replace("_seconds", "_seconds")
        if budget_name == "time":
            used_column = "time_used_seconds"
        row = self.conn.execute("SELECT * FROM budgets WHERE node_id = ?", (node_id,)).fetchone()
        if row is None:
            self.conn.execute(
                """
                INSERT INTO budgets(
                    node_id, attempt_budget, token_budget, time_budget_seconds,
                    tool_budget, branch_budget
                ) VALUES (?, 8, 200000, 3600, 50, 3)
                """,
                (node_id,),
            )
            row = self.conn.execute(
                "SELECT * FROM budgets WHERE node_id = ?", (node_id,)
            ).fetchone()
        current_used = float(row[used_column])
        self.conn.execute(
            f"UPDATE budgets SET {used_column} = ? WHERE node_id = ?",
            (current_used + amount, node_id),
        )
        limit = float(row[column])
        return limit - (current_used + amount)

    def start_run(
        self,
        run_id: str,
        role: str,
        *,
        node_scope: str | None = None,
        task_label: str = "",
        model_profile: str | None = None,
        reasoning_effort: str | None = None,
        resolved_model_id: str | None = None,
        status: str = RunStatus.RUNNING.value,
    ) -> None:
        existing = self.conn.execute(
            "SELECT id FROM agent_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if existing is not None:
            raise ValueError(f"Run already exists: {run_id}")
        now = utc_now().isoformat()
        self.conn.execute(
            """
            INSERT INTO agent_runs(
                id, role, status, node_scope, task_label, model_profile,
                reasoning_effort, resolved_model_id,
                started_at, updated_at, ended_at, last_result_summary,
                error_code, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)
            """,
            (
                run_id,
                role,
                status,
                node_scope,
                task_label,
                model_profile,
                reasoning_effort,
                resolved_model_id,
                now,
                now,
            ),
        )
        self._append_agent_event(run_id, "RUN_STARTED", task_label or "Run started", {})

    def transition_run(self, run_id: str, status: str, summary: str | None = None) -> None:
        row = self.conn.execute("SELECT status FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Run not found: {run_id}")
        assert_legal_transition(
            row["status"], status, LEGAL_RUN_TRANSITIONS, label="run"
        )
        now = utc_now().isoformat()
        self.conn.execute(
            """
            UPDATE agent_runs
            SET status = ?, updated_at = ?, last_result_summary = COALESCE(?, last_result_summary)
            WHERE id = ?
            """,
            (status, now, summary, run_id),
        )
        self._append_agent_event(run_id, "RUN_STATE", summary or status, {"status": status})

    def heartbeat_run(self, run_id: str, summary: str) -> None:
        self.conn.execute(
            "UPDATE agent_runs SET updated_at = ?, last_result_summary = ? WHERE id = ?",
            (utc_now().isoformat(), summary, run_id),
        )
        self._append_agent_event(run_id, "RUN_HEARTBEAT", summary, {})

    def complete_run(self, run_id: str, summary: str) -> None:
        now = utc_now().isoformat()
        self.conn.execute(
            """
            UPDATE agent_runs
            SET status = ?, updated_at = ?, ended_at = ?, last_result_summary = ?
            WHERE id = ?
            """,
            (RunStatus.FINISHED.value, now, now, summary, run_id),
        )
        self._append_agent_event(run_id, "RUN_COMPLETED", summary, {})

    def fail_run(self, run_id: str, code: str, message: str) -> None:
        now = utc_now().isoformat()
        self.conn.execute(
            """
            UPDATE agent_runs
            SET status = ?, updated_at = ?, ended_at = ?,
                error_code = ?, error_message = ?, last_result_summary = ?
            WHERE id = ?
            """,
            (RunStatus.FAILED.value, now, now, code, message, message, run_id),
        )
        self._append_agent_event(run_id, "RUN_FAILED", message, {"code": code})

    def cancel_run(self, run_id: str, reason: str = "cancelled") -> None:
        row = self.conn.execute("SELECT status FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Run not found: {run_id}")
        if row["status"] in TERMINAL_RUN_STATUSES:
            return
        assert_legal_transition(
            row["status"], RunStatus.CANCELLED.value, LEGAL_RUN_TRANSITIONS, label="run"
        )
        now = utc_now().isoformat()
        self.conn.execute(
            """
            UPDATE agent_runs
            SET status = ?, updated_at = ?, ended_at = ?, last_result_summary = ?
            WHERE id = ?
            """,
            (RunStatus.CANCELLED.value, now, now, reason, run_id),
        )
        self._append_agent_event(run_id, "RUN_CANCELLED", reason, {})

    def list_active_runs(self) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in ACTIVE_RUN_STATUSES)
        rows = self.conn.execute(
            f"""
            SELECT * FROM agent_runs
            WHERE status IN ({placeholders})
            ORDER BY started_at
            """,
            tuple(ACTIVE_RUN_STATUSES),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in TERMINAL_RUN_STATUSES)
        rows = self.conn.execute(
            f"""
            SELECT * FROM agent_runs
            WHERE status IN ({placeholders})
            ORDER BY ended_at DESC LIMIT ?
            """,
            (*TERMINAL_RUN_STATUSES, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_report_for_run(self, run_id: str) -> ResearchReport | None:
        row = self.conn.execute(
            "SELECT * FROM reports WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_report(row)

    def get_accepted_transaction_for_report(self, report_id: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT transaction_id FROM review_decisions
            WHERE report_id = ? AND transaction_id IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (report_id,),
        ).fetchone()
        return None if row is None else row["transaction_id"]

    def record_budget_usage(
        self,
        run_id: str,
        budget_name: str,
        amount: float,
        detail: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO run_budget_usage(run_id, budget_name, amount, detail, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, budget_name, amount, detail, utc_now().isoformat()),
        )

    def list_budget_usage(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT budget_name, amount, detail, created_at FROM run_budget_usage WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_stale_runs(self, stale_seconds: int) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in ACTIVE_RUN_STATUSES)
        rows = self.conn.execute(
            f"""
            SELECT * FROM agent_runs
            WHERE status IN ({placeholders})
            ORDER BY updated_at
            """,
            tuple(ACTIVE_RUN_STATUSES),
        ).fetchall()
        now = utc_now()
        stale: list[dict[str, Any]] = []
        for row in rows:
            updated = datetime.fromisoformat(row["updated_at"])
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            if (now - updated).total_seconds() > stale_seconds:
                stale.append(dict(row))
        return stale

    def _append_agent_event(
        self, run_id: str, event_type: str, summary: str, payload: dict
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO agent_events(run_id, event_type, summary, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, event_type, summary, json.dumps(payload), utc_now().isoformat()),
        )

    def get_latest_metric(self, node_id: str, metric_name: str) -> float | None:
        row = self.conn.execute(
            """
            SELECT value FROM metrics
            WHERE node_id = ? AND metric_name = ?
            ORDER BY id DESC LIMIT 1
            """,
            (node_id, metric_name),
        ).fetchone()
        return None if row is None else float(row["value"])

    def _row_to_object(self, row: sqlite3.Row) -> ResearchObject:
        prov = json.loads(row["provenance_json"])
        return ResearchObject(
            id=row["id"],
            type=row["type"],
            title=row["title"],
            statement=row["statement"],
            formalization=row["formalization"],
            status=row["status"],
            created_at=row["created_at"],
            admitted_at=row["admitted_at"],
            content_hash=row["content_hash"],
            equivalence_class_id=row["equivalence_class_id"],
            is_class_representative=bool(row["is_class_representative"]),
            provenance=Provenance(
                origin_kind=prov["origin_kind"],
                origin_refs=prov["origin_refs"],
                created_by_run=prov["created_by_run"],
            ),
            evidence_refs=json.loads(row["evidence_refs_json"]),
            tags=json.loads(row["tags_json"]),
            information_gain=row["information_gain"],
        )

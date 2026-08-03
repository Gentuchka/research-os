"""Repository for knowledge graph persistence."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from research_os.kernel.types import (
    AppendMetricOp,
    AppendNodeOp,
    ArchiveNodeOp,
    CreateLinkOp,
    MergeEquivalenceClassOp,
    Operation,
    Provenance,
    ResearchObject,
    SetStatusOp,
    SupersedeNodeOp,
    utc_now,
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
            WHERE payload_json LIKE ?
            ORDER BY id
            """,
            (f"%{node_id}%",),
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
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO transactions(
                id, actor_role, actor_run_id, summary, created_at,
                accepted, git_commit_sha, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tx_id,
                actor_role,
                actor_run_id,
                summary,
                utc_now().isoformat(),
                1 if accepted else 0,
                git_commit_sha,
                json.dumps(payload),
            ),
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
        self, tx_id: str, event_type: str, payload: dict[str, Any], now: str
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO events(event_type, payload_json, created_at, transaction_id)
            VALUES (?, ?, ?, ?)
            """,
            (event_type, json.dumps(payload), now, tx_id),
        )

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

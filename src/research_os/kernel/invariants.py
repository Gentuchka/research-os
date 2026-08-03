"""Invariant enforcement at transaction boundary."""

from __future__ import annotations

from collections import defaultdict, deque

from research_os.kernel.types import (
    AppendMetricOp,
    AppendNodeOp,
    ArchiveNodeOp,
    CreateLinkOp,
    InvariantCode,
    KernelError,
    MergeEquivalenceClassOp,
    Operation,
    SetStatusOp,
    SupersedeNodeOp,
    Transaction,
)
from research_os.store.repository import Repository

FACT_STATUSES = {"PROVED", "DISPROVED"}
OPINION_METRICS = {
    "importance",
    "difficulty",
    "novelty",
    "promise",
    "information_gain",
}


class InvariantEngine:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def validate(self, tx: Transaction) -> None:
        if not tx.ops:
            raise KernelError(
                InvariantCode.INVALID_OPERATION,
                "Transaction must contain operations",
            )
        pending_ids = {
            op.object.id for op in tx.ops if isinstance(op, AppendNodeOp)
        }
        for op in tx.ops:
            self._validate_op(op, pending_ids=pending_ids)
        self._validate_cycle_after_ops(tx.ops)

    def _validate_op(self, op: Operation, *, pending_ids: set[str]) -> None:
        if isinstance(op, AppendNodeOp):
            self._validate_append(op)
        elif isinstance(op, ArchiveNodeOp):
            self._require_exists(op.node_id, pending_ids)
        elif isinstance(op, SupersedeNodeOp):
            self._require_exists(op.old_id, pending_ids)
            self._require_exists(op.new_id, pending_ids)
        elif isinstance(op, CreateLinkOp):
            self._validate_link(op, pending_ids)
        elif isinstance(op, MergeEquivalenceClassOp):
            self._require_exists(op.representative_id, pending_ids)
            self._require_exists(op.member_id, pending_ids)
        elif isinstance(op, SetStatusOp):
            self._validate_status(op, pending_ids)
        elif isinstance(op, AppendMetricOp):
            self._validate_metric(op, pending_ids)
        else:
            raise KernelError(InvariantCode.INVALID_OPERATION, f"Unknown op: {op}")

    def _validate_append(self, op: AppendNodeOp) -> None:
        obj = op.object
        if self.repo.object_exists(obj.id):
            raise KernelError(
                InvariantCode.INV_IMMUTABLE_EDIT,
                f"Object already exists: {obj.id}",
            )
        if self.repo.content_hash_exists(obj.content_hash):
            raise KernelError(
                InvariantCode.DUPLICATE_CONTENT,
                f"Duplicate content hash: {obj.content_hash}",
            )
        if not obj.provenance.origin_refs:
            raise KernelError(
                InvariantCode.INV_NO_PROVENANCE,
                f"Missing provenance for {obj.id}",
            )
        if not obj.information_gain:
            raise KernelError(
                InvariantCode.INV_NO_INFO_GAIN,
                f"Missing information_gain for {obj.id}",
            )
        for ref in obj.provenance.origin_refs:
            if ref != "bootstrap" and not self.repo.object_exists(ref):
                raise KernelError(
                    InvariantCode.INV_NO_PROVENANCE,
                    f"Unknown provenance ref: {ref}",
                )

    def _validate_link(self, op: CreateLinkOp, pending_ids: set[str]) -> None:
        self._require_exists(op.from_id, pending_ids)
        self._require_exists(op.to_id, pending_ids)
        if op.graph == "math":
            allowed = {
                "strengthens",
                "weakens",
                "generalizes",
                "specializes",
                "depends_on",
                "uses",
                "proved_by",
                "disproved_by",
                "kills",
                "extends",
                "derived_from",
                "motivated_by",
                "requires",
                "supersedes",
                "cites",
            }
            if op.edge_type not in allowed:
                raise KernelError(
                    InvariantCode.INV_UNTYPED_EDGE,
                    f"Invalid math edge type: {op.edge_type}",
                )
        else:
            if not op.edge_type.startswith("prov:"):
                raise KernelError(
                    InvariantCode.INV_UNTYPED_EDGE,
                    f"Invalid provenance edge type: {op.edge_type}",
                )

    def _validate_status(self, op: SetStatusOp, pending_ids: set[str]) -> None:
        self._require_exists(op.node_id, pending_ids)
        if op.status in FACT_STATUSES and not op.evidence_refs:
            raise KernelError(
                InvariantCode.INV_UNSUPPORTED_CLAIM,
                f"Status {op.status} requires evidence_refs",
            )

    def _validate_metric(self, op: AppendMetricOp, pending_ids: set[str]) -> None:
        self._require_exists(op.node_id, pending_ids)
        if op.metric_name not in OPINION_METRICS:
            raise KernelError(
                InvariantCode.INV_FACT_OPINION_MIX,
                f"Metric {op.metric_name} is not an allowed opinion metric",
            )

    def _validate_cycle_after_ops(self, ops: list[Operation]) -> None:
        edges = list(self.repo.list_math_edges())
        for op in ops:
            if isinstance(op, CreateLinkOp) and op.graph == "math":
                edges.append((op.from_id, op.to_id, op.edge_type))
            if isinstance(op, SupersedeNodeOp):
                edges.append((op.new_id, op.old_id, "supersedes"))
        if _has_cycle(edges):
            raise KernelError(InvariantCode.INV_CYCLE, "Mathematical graph would contain a cycle")

    def _require_exists(self, node_id: str, pending_ids: set[str] | None = None) -> None:
        if pending_ids and node_id in pending_ids:
            return
        if not self.repo.object_exists(node_id):
            raise KernelError(InvariantCode.NOT_FOUND, f"Object not found: {node_id}")


def _has_cycle(edges: list[tuple[str, str, str]]) -> bool:
    graph: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = set()
    for src, dst, _ in edges:
        graph[src].append(dst)
        nodes.add(src)
        nodes.add(dst)
    indegree = {node: 0 for node in nodes}
    for src in graph:
        for dst in graph[src]:
            indegree[dst] += 1
    queue = deque([node for node in nodes if indegree[node] == 0])
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for nxt in graph[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return visited != len(nodes)

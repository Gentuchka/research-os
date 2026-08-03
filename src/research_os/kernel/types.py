"""Kernel types, IDs, hashing, and transaction envelopes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from ulid import ULID

TYPE_PREFIX: dict[str, str] = {
    "MainConjecture": "mc",
    "Hypothesis": "hyp",
    "Lemma": "lem",
    "Definition": "def",
    "Technique": "tec",
    "Construction": "con",
    "Counterexample": "cex",
    "Observation": "obs",
    "Proof": "prf",
    "FailedAttempt": "fat",
    "ResearchQuestion": "rq",
    "Experiment": "exp",
    "Paper": "pap",
    "Report": "rpt",
    "DeadEnd": "ded",
}


class ObjectType(StrEnum):
    MAIN_CONJECTURE = "MainConjecture"
    HYPOTHESIS = "Hypothesis"
    LEMMA = "Lemma"
    DEFINITION = "Definition"
    TECHNIQUE = "Technique"
    CONSTRUCTION = "Construction"
    COUNTEREXAMPLE = "Counterexample"
    OBSERVATION = "Observation"
    PROOF = "Proof"
    FAILED_ATTEMPT = "FailedAttempt"
    RESEARCH_QUESTION = "ResearchQuestion"
    EXPERIMENT = "Experiment"
    PAPER = "Paper"
    REPORT = "Report"
    DEAD_END = "DeadEnd"


class Status(StrEnum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    PROVED = "PROVED"
    DISPROVED = "DISPROVED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"
    STUCK = "STUCK"
    FROZEN = "FROZEN"
    REJECTED = "REJECTED"


class MathEdgeType(StrEnum):
    STRENGTHENS = "strengthens"
    WEAKENS = "weakens"
    GENERALIZES = "generalizes"
    SPECIALIZES = "specializes"
    DEPENDS_ON = "depends_on"
    USES = "uses"
    PROVED_BY = "proved_by"
    DISPROVED_BY = "disproved_by"
    KILLS = "kills"
    EXTENDS = "extends"
    DERIVED_FROM = "derived_from"
    MOTIVATED_BY = "motivated_by"
    REQUIRES = "requires"
    SUPERSEDES = "supersedes"
    CITES = "cites"


class ProvEdgeType(StrEnum):
    PRODUCED = "prov:produced"
    INSPIRED = "prov:inspired"
    SUPPORTED_BY = "prov:supported_by"
    FROM_LITERATURE = "prov:from_literature"
    HUMAN_INJECTED = "prov:human_injected"
    MEMBER_OF_CLASS = "prov:member_of_class"


class OriginKind(StrEnum):
    MAIN_CONJECTURE = "main_conjecture"
    WORKER_REPORT = "worker_report"
    THINKER_PROPOSAL = "thinker_proposal"
    LITERATURE = "literature"
    EXISTING_HYPOTHESIS = "existing_hypothesis"
    HUMAN_DIRECTIVE = "human_directive"


class AgentRole(StrEnum):
    WORKER = "worker"
    REVIEWER = "reviewer"
    THINKER = "thinker"
    SCHEDULER = "scheduler"
    HUMAN = "human"


class InvariantCode(StrEnum):
    INV_CYCLE = "INV_CYCLE"
    INV_NO_PROVENANCE = "INV_NO_PROVENANCE"
    INV_NO_INFO_GAIN = "INV_NO_INFO_GAIN"
    INV_UNTYPED_EDGE = "INV_UNTYPED_EDGE"
    INV_FACT_OPINION_MIX = "INV_FACT_OPINION_MIX"
    INV_UNSUPPORTED_CLAIM = "INV_UNSUPPORTED_CLAIM"
    INV_IMMUTABLE_EDIT = "INV_IMMUTABLE_EDIT"
    ACL_DENIED = "ACL_DENIED"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    SLOP_REJECTED = "SLOP_REJECTED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_OPERATION = "INVALID_OPERATION"


class KernelError(Exception):
    def __init__(self, code: InvariantCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code.value}: {message}")


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(object_type: str) -> str:
    prefix = TYPE_PREFIX.get(object_type)
    if prefix is None:
        raise KernelError(InvariantCode.INVALID_OPERATION, f"Unknown object type: {object_type}")
    return f"ros_{prefix}_{ULID()}"


def new_tx_id() -> str:
    return f"ros_tx_{ULID()}"


def new_class_id() -> str:
    return f"ros_eq_{ULID()}"


def canonical_content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class Provenance:
    origin_kind: str
    origin_refs: list[str]
    created_by_run: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin_kind": self.origin_kind,
            "origin_refs": self.origin_refs,
            "created_by_run": self.created_by_run,
        }


@dataclass(frozen=True)
class ResearchObject:
    id: str
    type: str
    title: str
    statement: str
    status: str
    created_at: str
    content_hash: str
    provenance: Provenance
    formalization: str | None = None
    admitted_at: str | None = None
    equivalence_class_id: str | None = None
    is_class_representative: bool = True
    evidence_refs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    information_gain: str | None = None

    def content_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "title": self.title,
            "statement": self.statement,
            "formalization": self.formalization,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "statement": self.statement,
            "formalization": self.formalization,
            "status": self.status,
            "created_at": self.created_at,
            "admitted_at": self.admitted_at,
            "content_hash": self.content_hash,
            "equivalence_class_id": self.equivalence_class_id,
            "is_class_representative": self.is_class_representative,
            "provenance": self.provenance.to_dict(),
            "evidence_refs": self.evidence_refs,
            "tags": self.tags,
            "information_gain": self.information_gain,
        }


@dataclass(frozen=True)
class RoleContext:
    role: AgentRole
    run_id: str
    node_scope: str | None = None


@dataclass(frozen=True)
class AppendNodeOp:
    object: ResearchObject

    @property
    def op_type(self) -> str:
        return "append_node"


@dataclass(frozen=True)
class ArchiveNodeOp:
    node_id: str
    reason: str

    @property
    def op_type(self) -> str:
        return "archive_node"


@dataclass(frozen=True)
class SupersedeNodeOp:
    old_id: str
    new_id: str
    reason: str

    @property
    def op_type(self) -> str:
        return "supersede_node"


@dataclass(frozen=True)
class CreateLinkOp:
    from_id: str
    to_id: str
    edge_type: str
    graph: str = "math"

    @property
    def op_type(self) -> str:
        return "create_link"


@dataclass(frozen=True)
class MergeEquivalenceClassOp:
    representative_id: str
    member_id: str
    class_id: str | None = None

    @property
    def op_type(self) -> str:
        return "merge_equivalence_class"


@dataclass(frozen=True)
class SetStatusOp:
    node_id: str
    status: str
    evidence_refs: list[str]
    reason: str

    @property
    def op_type(self) -> str:
        return "set_status"


@dataclass(frozen=True)
class AppendMetricOp:
    node_id: str
    metric_name: str
    value: float
    method: str
    version: str

    @property
    def op_type(self) -> str:
        return "append_metric"


Operation = (
    AppendNodeOp
    | ArchiveNodeOp
    | SupersedeNodeOp
    | CreateLinkOp
    | MergeEquivalenceClassOp
    | SetStatusOp
    | AppendMetricOp
)


@dataclass(frozen=True)
class Transaction:
    id: str
    actor_role: str
    actor_run_id: str
    ops: list[Operation]
    summary: str
    created_at: str = field(default_factory=lambda: utc_now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "actor_role": self.actor_role,
            "actor_run_id": self.actor_run_id,
            "summary": self.summary,
            "created_at": self.created_at,
            "ops": [serialize_op(op) for op in self.ops],
        }


def serialize_op(op: Operation) -> dict[str, Any]:
    if isinstance(op, AppendNodeOp):
        return {"op_type": "append_node", "object": op.object.to_dict()}
    if isinstance(op, ArchiveNodeOp):
        return {"op_type": "archive_node", "node_id": op.node_id, "reason": op.reason}
    if isinstance(op, SupersedeNodeOp):
        return {
            "op_type": "supersede_node",
            "old_id": op.old_id,
            "new_id": op.new_id,
            "reason": op.reason,
        }
    if isinstance(op, CreateLinkOp):
        return {
            "op_type": "create_link",
            "from_id": op.from_id,
            "to_id": op.to_id,
            "edge_type": op.edge_type,
            "graph": op.graph,
        }
    if isinstance(op, MergeEquivalenceClassOp):
        return {
            "op_type": "merge_equivalence_class",
            "representative_id": op.representative_id,
            "member_id": op.member_id,
            "class_id": op.class_id,
        }
    if isinstance(op, SetStatusOp):
        return {
            "op_type": "set_status",
            "node_id": op.node_id,
            "status": op.status,
            "evidence_refs": op.evidence_refs,
            "reason": op.reason,
        }
    if isinstance(op, AppendMetricOp):
        return {
            "op_type": "append_metric",
            "node_id": op.node_id,
            "metric_name": op.metric_name,
            "value": op.value,
            "method": op.method,
            "version": op.version,
        }
    raise ValueError(f"Unknown operation: {op}")

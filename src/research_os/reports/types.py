"""Report domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from research_os.kernel.types import new_id, utc_now


class ReportStatus(StrEnum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    ACCEPTED = "ACCEPTED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


class ReviewDecisionKind(StrEnum):
    ACCEPT = "ACCEPT"
    PARTIAL_ACCEPT = "PARTIAL_ACCEPT"
    REJECT = "REJECT"
    NEEDS_HUMAN = "NEEDS_HUMAN"


@dataclass(frozen=True)
class ResearchReport:
    id: str
    report_type: str
    subject_node_id: str
    status: str
    run_id: str
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "report_type": self.report_type,
            "subject_node_id": self.subject_node_id,
            "status": self.status,
            "run_id": self.run_id,
            "payload": self.payload,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ReviewDecision:
    id: str
    report_id: str
    decision: str
    reason_codes: list[str]
    reviewer_run_id: str
    transaction_id: str | None
    created_at: str
    accepted_claim_indices: list[int] = field(default_factory=list)
    rejected_claim_indices: list[int] = field(default_factory=list)


def new_report_id() -> str:
    return new_id("Report")


def new_decision_id() -> str:
    return f"ros_dec_{utc_now().strftime('%Y%m%d%H%M%S%f')}"

"""Reviewer adjudication and transaction building."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research_os.anti_slop.engine import AntiSlopEngine
from research_os.kernel.builders import build_object
from research_os.kernel.transaction_service import TransactionService
from research_os.kernel.types import (
    AgentRole,
    AppendNodeOp,
    CreateLinkOp,
    RoleContext,
    Transaction,
    new_tx_id,
    utc_now,
)
from research_os.metrics.engine import MetricsEngine
from research_os.projection.activity import ActivityProjector
from research_os.projection.vault import VaultProjector
from research_os.reports.types import (
    ReportStatus,
    ReviewDecision,
    ReviewDecisionKind,
    new_decision_id,
)
from research_os.store.repository import Repository


@dataclass
class AdjudicationOutcome:
    decision: str
    reason_codes: list[str]
    transaction: Transaction | None
    apply_result: Any | None = None


class ReviewerService:
    def __init__(
        self,
        repo: Repository,
        tx_service: TransactionService,
        anti_slop: AntiSlopEngine,
        metrics: MetricsEngine,
        vault: VaultProjector,
        activity: ActivityProjector,
    ) -> None:
        self.repo = repo
        self.tx_service = tx_service
        self.anti_slop = anti_slop
        self.metrics = metrics
        self.vault = vault
        self.activity = activity

    def review_report(self, ctx: RoleContext, report_id: str) -> AdjudicationOutcome:
        if ctx.role not in {AgentRole.REVIEWER, AgentRole.HUMAN}:
            raise PermissionError("Only reviewer/human can review reports")
        report = self.repo.get_report(report_id)
        if report is None:
            raise ValueError(f"Report not found: {report_id}")

        findings = self.anti_slop.check_report(report.payload, run_id=report.run_id)
        blocking = [f for f in findings if f.code.startswith("SLOP_")]
        if blocking:
            decision = ReviewDecision(
                id=new_decision_id(),
                report_id=report_id,
                decision=ReviewDecisionKind.REJECT.value,
                reason_codes=[f.code for f in blocking],
                reviewer_run_id=ctx.run_id,
                transaction_id=None,
                created_at=utc_now().isoformat(),
            )
            self.repo.save_review_decision(decision)
            self.repo.update_report_status(report_id, ReportStatus.REJECTED.value)
            self.repo.conn.commit()
            self.vault.project_report(report, decision)
            self.activity.project_dashboard()
            return AdjudicationOutcome(
                decision=ReviewDecisionKind.REJECT.value,
                reason_codes=decision.reason_codes,
                transaction=None,
            )

        ops = self._build_ops(report, ctx.run_id)
        if not ops:
            decision = ReviewDecision(
                id=new_decision_id(),
                report_id=report_id,
                decision=ReviewDecisionKind.REJECT.value,
                reason_codes=["SLOP_LOW_INFORMATION"],
                reviewer_run_id=ctx.run_id,
                transaction_id=None,
                created_at=utc_now().isoformat(),
            )
            self.repo.save_review_decision(decision)
            self.repo.update_report_status(report_id, ReportStatus.REJECTED.value)
            self.repo.conn.commit()
            self.vault.project_report(report, decision)
            self.activity.project_dashboard()
            return AdjudicationOutcome(
                decision=ReviewDecisionKind.REJECT.value,
                reason_codes=decision.reason_codes,
                transaction=None,
            )

        tx = Transaction(
            id=new_tx_id(),
            actor_role=ctx.role.value,
            actor_run_id=ctx.run_id,
            summary=f"Accept report {report_id}",
            ops=ops,
        )
        apply_result = self.tx_service.apply(ctx, tx)
        decision_kind = (
            ReviewDecisionKind.ACCEPT.value
            if apply_result.accepted
            else ReviewDecisionKind.REJECT.value
        )
        reason_codes = (
            [] if apply_result.accepted else [r["code"] for r in apply_result.rejections]
        )
        decision = ReviewDecision(
            id=new_decision_id(),
            report_id=report_id,
            decision=decision_kind,
            reason_codes=reason_codes,
            reviewer_run_id=ctx.run_id,
            transaction_id=tx.id if apply_result.accepted else None,
            created_at=utc_now().isoformat(),
        )
        self.repo.save_review_decision(decision)
        status = (
            ReportStatus.ACCEPTED.value
            if apply_result.accepted
            else ReportStatus.REJECTED.value
        )
        self.repo.update_report_status(report_id, status)
        self.repo.conn.commit()
        if apply_result.accepted:
            self.metrics.recompute([op.object.id for op in ops if isinstance(op, AppendNodeOp)])
            self.metrics.recompute([report.subject_node_id])
        self.vault.project_report(report, decision)
        self.activity.project_dashboard()
        return AdjudicationOutcome(
            decision=decision_kind,
            reason_codes=decision.reason_codes,
            transaction=tx,
            apply_result=apply_result,
        )

    def _build_ops(self, report, run_id: str) -> list:
        ops = []
        created_ids: dict[int, str] = {}
        payload = report.payload
        for idx, proposed in enumerate(payload.get("proposed_objects", [])):
            obj = build_object(
                object_type=proposed["type"],
                title=proposed["title"],
                statement=proposed["statement"],
                origin_kind="worker_report",
                origin_refs=[report.subject_node_id],
                run_id=run_id,
                information_gain=proposed["information_gain"],
            )
            created_ids[idx] = obj.id
            ops.append(AppendNodeOp(object=obj))

        for link in payload.get("proposed_links", []):
            from_id = link["from_id"]
            to_id = link["to_id"]
            if from_id.startswith("$new:"):
                from_id = created_ids[int(from_id.split(":")[1])]
            if to_id.startswith("$new:"):
                to_id = created_ids[int(to_id.split(":")[1])]
            ops.append(
                CreateLinkOp(
                    from_id=from_id,
                    to_id=to_id,
                    edge_type=link["edge_type"],
                    graph=link.get("graph", "math"),
                )
            )
        return ops

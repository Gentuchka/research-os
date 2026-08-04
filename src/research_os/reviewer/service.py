"""Reviewer adjudication and transaction building."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_os.anti_slop.engine import AntiSlopEngine, SlopFinding
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
    accepted_claim_indices: list[int] | None = None
    rejected_claim_indices: list[int] | None = None


class ReviewerService:
    def __init__(
        self,
        repo: Repository,
        tx_service: TransactionService,
        anti_slop: AntiSlopEngine,
        metrics: MetricsEngine,
        vault: VaultProjector,
        activity: ActivityProjector,
        rejections_dir: Path | None = None,
    ) -> None:
        self.repo = repo
        self.tx_service = tx_service
        self.anti_slop = anti_slop
        self.metrics = metrics
        self.vault = vault
        self.activity = activity
        self.rejections_dir = rejections_dir

    def review_report(self, ctx: RoleContext, report_id: str) -> AdjudicationOutcome:
        if ctx.role not in {AgentRole.REVIEWER, AgentRole.HUMAN}:
            raise PermissionError("Only reviewer/human can review reports")
        report = self.repo.get_report(report_id)
        if report is None:
            raise ValueError(f"Report not found: {report_id}")

        if report.status != ReportStatus.PENDING.value:
            existing = self.repo.get_latest_decision(report_id)
            if existing is not None:
                return AdjudicationOutcome(
                    decision=existing.decision,
                    reason_codes=existing.reason_codes,
                    transaction=None,
                    accepted_claim_indices=existing.accepted_claim_indices,
                    rejected_claim_indices=existing.rejected_claim_indices,
                )
            raise ValueError(f"Report {report_id} is not pending review")

        self.repo.update_report_status(report_id, ReportStatus.IN_REVIEW.value)
        self.repo.conn.commit()

        if report.payload.get("needs_human"):
            return self._finalize(
                report,
                ctx,
                ReviewDecisionKind.NEEDS_HUMAN.value,
                ["NEEDS_HUMAN"],
                [],
                list(range(len(report.payload.get("claims", [])))),
                None,
                None,
                ReportStatus.PENDING.value,
            )

        findings = self.anti_slop.check_report(report.payload, run_id=report.run_id)
        blocking = [f for f in findings if f.code.startswith("SLOP_") and f.claim_index is None]
        if blocking:
            return self._finalize(
                report,
                ctx,
                ReviewDecisionKind.REJECT.value,
                [f.code for f in blocking],
                [],
                list(range(len(report.payload.get("claims", [])))),
                None,
                None,
                ReportStatus.REJECTED.value,
            )

        accepted, rejected, claim_reasons = self._partition_claims(report.payload, findings)
        ops = self._build_ops(report, ctx.run_id, accepted)
        if not ops:
            reason_codes = claim_reasons or ["SLOP_LOW_INFORMATION"]
            return self._finalize(
                report,
                ctx,
                ReviewDecisionKind.REJECT.value,
                reason_codes,
                [],
                rejected or list(range(len(report.payload.get("claims", [])))),
                None,
                None,
                ReportStatus.REJECTED.value,
            )

        if rejected and accepted:
            decision_kind = ReviewDecisionKind.PARTIAL_ACCEPT.value
            report_status = ReportStatus.PARTIAL.value
        else:
            decision_kind = ReviewDecisionKind.ACCEPT.value
            report_status = ReportStatus.ACCEPTED.value

        tx = Transaction(
            id=new_tx_id(),
            actor_role=ctx.role.value,
            actor_run_id=ctx.run_id,
            summary=f"Accept report {report_id}",
            ops=ops,
        )
        apply_result = self.tx_service.apply(ctx, tx)
        if not apply_result.accepted:
            return self._finalize(
                report,
                ctx,
                ReviewDecisionKind.REJECT.value,
                [r["code"] for r in apply_result.rejections],
                [],
                list(range(len(report.payload.get("claims", [])))),
                tx,
                apply_result,
                ReportStatus.REJECTED.value,
            )

        self.metrics.recompute([op.object.id for op in ops if isinstance(op, AppendNodeOp)])
        self.metrics.recompute([report.subject_node_id])
        return self._finalize(
            report,
            ctx,
            decision_kind,
            claim_reasons,
            accepted,
            rejected,
            tx,
            apply_result,
            report_status,
        )

    def _partition_claims(
        self,
        payload: dict[str, Any],
        findings: list[SlopFinding],
    ) -> tuple[list[int], list[int], list[str]]:
        claims = payload.get("claims", [])
        accepted: list[int] = []
        rejected: list[int] = []
        reason_codes: list[str] = []
        for idx, claim in enumerate(claims):
            claim_findings = [f for f in findings if f.claim_index == idx]
            if claim.get("accept") is False or claim_findings:
                rejected.append(idx)
                reason_codes.extend(f.code for f in claim_findings)
            else:
                accepted.append(idx)
        return accepted, rejected, sorted(set(reason_codes))

    def _finalize(
        self,
        report,
        ctx: RoleContext,
        decision_kind: str,
        reason_codes: list[str],
        accepted_claim_indices: list[int],
        rejected_claim_indices: list[int],
        tx: Transaction | None,
        apply_result: Any | None,
        report_status: str,
    ) -> AdjudicationOutcome:
        decision = ReviewDecision(
            id=new_decision_id(),
            report_id=report.id,
            decision=decision_kind,
            reason_codes=reason_codes,
            reviewer_run_id=ctx.run_id,
            transaction_id=tx.id if apply_result and apply_result.accepted else None,
            created_at=utc_now().isoformat(),
            accepted_claim_indices=accepted_claim_indices,
            rejected_claim_indices=rejected_claim_indices,
        )
        self.repo.save_review_decision(decision)
        self.repo.update_report_status(report.id, report_status)
        self.repo.close_review_queue(report.id, ctx.run_id)
        self.repo.conn.commit()
        self.vault.project_report(report, decision, accepted_claim_indices, rejected_claim_indices)
        if decision_kind == ReviewDecisionKind.REJECT.value:
            self._export_rejection(report, decision)
        self.activity.project_dashboard(force=True)
        return AdjudicationOutcome(
            decision=decision_kind,
            reason_codes=reason_codes,
            transaction=tx,
            apply_result=apply_result,
            accepted_claim_indices=accepted_claim_indices,
            rejected_claim_indices=rejected_claim_indices,
        )

    def _export_rejection(self, report, decision: ReviewDecision) -> None:
        if self.rejections_dir is None:
            return
        self.rejections_dir.mkdir(parents=True, exist_ok=True)
        path = self.rejections_dir / f"{report.id}.json"
        path.write_text(
            json.dumps(
                {
                    "report_id": report.id,
                    "decision": decision.decision,
                    "reason_codes": decision.reason_codes,
                    "rejected_claim_indices": decision.rejected_claim_indices,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _build_ops(self, report, run_id: str, accepted_claim_indices: list[int]) -> list:
        ops = []
        created_ids: dict[int, str] = {}
        payload = report.payload
        accepted_set = set(accepted_claim_indices)
        for idx, proposed in enumerate(payload.get("proposed_objects", [])):
            claim_index = proposed.get("claim_index")
            if claim_index is not None and claim_index not in accepted_set:
                continue
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
                new_idx = int(from_id.split(":")[1])
                if new_idx not in created_ids:
                    continue
                from_id = created_ids[new_idx]
            if to_id.startswith("$new:"):
                new_idx = int(to_id.split(":")[1])
                if new_idx not in created_ids:
                    continue
                to_id = created_ids[new_idx]
            ops.append(
                CreateLinkOp(
                    from_id=from_id,
                    to_id=to_id,
                    edge_type=link["edge_type"],
                    graph=link.get("graph", "math"),
                )
            )
        return ops

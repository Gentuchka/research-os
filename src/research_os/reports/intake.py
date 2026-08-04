"""Report intake and persistence."""

from __future__ import annotations

from typing import Any

from research_os.kernel.types import RoleContext, utc_now
from research_os.reports.types import ReportStatus, ResearchReport, new_report_id
from research_os.store.repository import Repository
from research_os.validation.schema import validate_instance


class ReportIntake:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def submit(self, ctx: RoleContext, payload: dict[str, Any]) -> ResearchReport:
        validate_instance("reports.schema.json", payload)
        if not self.repo.object_exists(payload["subject_node_id"]):
            raise ValueError(f"Subject node not found: {payload['subject_node_id']}")

        fingerprint = self.repo._report_fingerprint(payload)

        existing_for_run = self.repo.get_report_for_run(ctx.run_id)
        if existing_for_run is not None:
            existing_fp = self.repo._report_fingerprint(existing_for_run.payload)
            if fingerprint == existing_fp:
                return existing_for_run
            raise ValueError(
                f"Run {ctx.run_id} already submitted report {existing_for_run.id}; "
                "different content is not allowed"
            )

        existing = self.repo.get_report_by_fingerprint(fingerprint)
        if existing is not None:
            return existing

        report = ResearchReport(
            id=new_report_id(),
            report_type=payload["report_type"],
            subject_node_id=payload["subject_node_id"],
            status=ReportStatus.PENDING.value,
            run_id=ctx.run_id,
            payload=payload,
            created_at=utc_now().isoformat(),
        )
        self.repo.save_report(report)
        self.repo.enqueue_review(report.id, ctx.run_id)
        self.repo.conn.commit()
        return report

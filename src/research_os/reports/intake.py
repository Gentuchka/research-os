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

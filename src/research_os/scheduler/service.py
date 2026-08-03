"""Minimal scheduler for worker dispatch."""

from __future__ import annotations

from typing import Any

from research_os.agents.worker.runtime import WorkerRuntime
from research_os.config import RuntimeConfig
from research_os.kernel.types import AgentRole, RoleContext
from research_os.metrics.engine import MetricsEngine
from research_os.projection.activity import ActivityProjector
from research_os.reports.intake import ReportIntake
from research_os.reviewer.service import ReviewerService
from research_os.store.repository import Repository


class SchedulerService:
    def __init__(
        self,
        repo: Repository,
        report_intake: ReportIntake,
        reviewer: ReviewerService,
        metrics: MetricsEngine,
        activity: ActivityProjector,
        config: RuntimeConfig,
    ) -> None:
        self.repo = repo
        self.report_intake = report_intake
        self.reviewer = reviewer
        self.metrics = metrics
        self.activity = activity
        self.config = config
        self.worker_runtime = WorkerRuntime(repo, report_intake, activity, config)

    def dispatch_next(self, *, node_id: str | None = None) -> dict[str, Any]:
        frontier = self.metrics.ranked_frontier(limit=5)
        if not frontier and node_id is None:
            return {"status": "idle", "reason": "no frontier nodes"}
        target = node_id or frontier[0]["id"]
        run_id = f"run_worker_{target[-6:]}"
        resolved = self.worker_runtime.model_resolver.resolve_worker_profile()
        self.repo.start_run(
            run_id,
            AgentRole.WORKER.value,
            node_scope=target,
            task_label=f"Investigate {target}",
            model_profile=resolved.profile_name,
        )
        self.repo.record_budget_usage(run_id, "dispatch", 1.0, resolved.model_id)
        self.repo.conn.commit()
        self.activity.project_dashboard(force=True)
        report = self.worker_runtime.run_investigation(
            RoleContext(role=AgentRole.WORKER, run_id=run_id, node_scope=target),
            target,
        )
        self.repo.complete_run(run_id, f"Submitted report {report.id}")
        self.repo.conn.commit()
        self.activity.project_dashboard(force=True)
        review_ctx = RoleContext(role=AgentRole.REVIEWER, run_id=f"run_reviewer_{run_id[-6:]}")
        outcome = self.reviewer.review_report(review_ctx, report.id)
        return {
            "status": "completed",
            "node_id": target,
            "worker_run_id": run_id,
            "report_id": report.id,
            "decision": outcome.decision,
            "reason_codes": outcome.reason_codes,
            "model": self.worker_runtime.model_resolver.profile_summary(resolved),
        }

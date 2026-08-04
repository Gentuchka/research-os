"""Minimal scheduler for worker dispatch."""

from __future__ import annotations

from typing import Any

from ulid import ULID

from research_os.agents.worker.runtime import WorkerRuntime
from research_os.config import RuntimeConfig
from research_os.kernel.types import AgentRole, RoleContext
from research_os.metrics.engine import MetricsEngine
from research_os.projection.activity import ActivityProjector
from research_os.reports.intake import ReportIntake
from research_os.reviewer.service import ReviewerService
from research_os.store.repository import Repository
from research_os.store.run_lifecycle import RunStatus


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
        if not self.repo.has_attempt_budget(target):
            return {
                "status": "blocked",
                "node_id": target,
                "reason": f"Attempt budget exhausted for {target}",
            }

        job_id = f"ros_job_{ULID()}"
        run_id = f"run_worker_{ULID()}"
        review_run_id = f"run_reviewer_{ULID()}"
        resolved = self.worker_runtime.model_resolver.resolve_worker_profile()
        self.repo.create_job(job_id, target)
        self.repo.update_job_status(job_id, RunStatus.STARTING.value, assigned_run_id=run_id)
        self.repo.start_run(
            run_id,
            AgentRole.WORKER.value,
            node_scope=target,
            task_label=f"Investigate {target}",
            model_profile=resolved.profile_name,
            reasoning_effort=resolved.reasoning_effort,
            resolved_model_id=resolved.model_id,
            status=RunStatus.STARTING.value,
        )
        self.repo.transition_run(run_id, RunStatus.RUNNING.value, "Worker starting")
        self.repo.update_job_status(job_id, RunStatus.RUNNING.value, assigned_run_id=run_id)
        self.repo.consume_node_budget(target, "attempt", 1.0)
        self.repo.record_budget_usage(run_id, "dispatch", 1.0, resolved.model_id)
        self.repo.conn.commit()
        self.activity.project_dashboard(force=True)

        report = None
        try:
            report = self.worker_runtime.run_investigation(
                RoleContext(role=AgentRole.WORKER, run_id=run_id, node_scope=target),
                target,
            )
            self.repo.transition_run(
                run_id,
                RunStatus.WAITING_FOR_REVIEW.value,
                f"Submitted report {report.id}",
            )
            self.repo.update_job_status(job_id, RunStatus.WAITING_FOR_REVIEW.value)
            self.repo.conn.commit()
            self.activity.project_dashboard(force=True)
        except Exception as exc:
            self._fail_worker(job_id, run_id, target, str(exc))
            return {
                "status": "failed",
                "node_id": target,
                "job_id": job_id,
                "worker_run_id": run_id,
                "reason": str(exc),
            }

        try:
            self.repo.start_run(
                review_run_id,
                AgentRole.REVIEWER.value,
                node_scope=target,
                task_label=f"Review {report.id}",
                status=RunStatus.REVIEWING.value,
            )
            self.repo.update_job_status(job_id, RunStatus.REVIEWING.value)
            outcome = self.reviewer.review_report(
                RoleContext(role=AgentRole.REVIEWER, run_id=review_run_id, node_scope=target),
                report.id,
            )
            self.repo.complete_run(review_run_id, f"Reviewed {report.id} as {outcome.decision}")
            self.repo.complete_run(run_id, f"Finished with {outcome.decision}")
            self.repo.update_job_status(job_id, RunStatus.FINISHED.value)
            self.repo.conn.commit()
            self.activity.project_dashboard(force=True)
            return {
                "status": "completed",
                "node_id": target,
                "job_id": job_id,
                "worker_run_id": run_id,
                "reviewer_run_id": review_run_id,
                "report_id": report.id,
                "decision": outcome.decision,
                "reason_codes": outcome.reason_codes,
                "model": self.worker_runtime.model_resolver.profile_summary(resolved),
            }
        except Exception as exc:
            self._fail_reviewer(job_id, run_id, review_run_id, report.id, str(exc))
            return {
                "status": "failed",
                "node_id": target,
                "job_id": job_id,
                "worker_run_id": run_id,
                "reviewer_run_id": review_run_id,
                "report_id": report.id,
                "reason": str(exc),
            }

    def _fail_worker(self, job_id: str, run_id: str, node_id: str, message: str) -> None:
        self.repo.fail_run(run_id, "WORKER_FAILED", message)
        self.repo.update_job_status(job_id, RunStatus.FAILED.value)
        self.repo.conn.commit()
        self.activity.project_dashboard(force=True)

    def _fail_reviewer(
        self,
        job_id: str,
        worker_run_id: str,
        review_run_id: str,
        report_id: str,
        message: str,
    ) -> None:
        self.repo.fail_run(review_run_id, "REVIEWER_FAILED", message)
        self.repo.transition_run(
            worker_run_id,
            RunStatus.WAITING_FOR_REVIEW.value,
            f"Reviewer failed for {report_id}",
        )
        self.repo.update_job_status(job_id, RunStatus.WAITING_FOR_REVIEW.value)
        self.repo.conn.commit()
        self.activity.project_dashboard(force=True)

    def cancel_run(self, run_id: str, reason: str = "cancelled by operator") -> dict[str, Any]:
        sdk_run_id = self.repo.get_sdk_run_id(run_id)
        if sdk_run_id:
            self._cancel_sdk_run(sdk_run_id)
        self.repo.cancel_run(run_id, reason)
        rows = self.repo.conn.execute(
            "SELECT id FROM jobs WHERE assigned_run_id = ?",
            (run_id,),
        ).fetchall()
        for row in rows:
            self.repo.update_job_status(row["id"], RunStatus.CANCELLED.value)
        self.repo.conn.commit()
        self.activity.project_dashboard(force=True)
        return {"status": "cancelled", "run_id": run_id, "reason": reason}

    def _cancel_sdk_run(self, sdk_run_id: str) -> None:
        try:
            from cursor_sdk import Agent

            run = Agent.get_run(sdk_run_id)
            if hasattr(run, "cancel"):
                run.cancel()
        except Exception:
            return

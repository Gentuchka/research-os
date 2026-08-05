"""Human-readable Obsidian activity dashboard."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_os.store.repository import Repository


class ActivityProjector:
    def __init__(
        self,
        repo: Repository,
        vault_dir: Path,
        activity_config: dict[str, Any] | None = None,
    ) -> None:
        self.repo = repo
        self.vault_dir = vault_dir
        self.activity_config = activity_config or {}
        self._last_refresh: datetime | None = None

    def project_dashboard(
        self, *, force: bool = False, throttle_seconds: int | None = None
    ) -> Path:
        throttle = throttle_seconds or int(self.activity_config.get("refresh_throttle_seconds", 5))
        now = datetime.now(UTC)
        if (
            not force
            and self._last_refresh is not None
            and (now - self._last_refresh).total_seconds() < throttle
        ):
            return self.vault_dir / "00_meta" / "AGENT_ACTIVITY.md"
        self._last_refresh = now
        path = self.vault_dir / "00_meta" / "AGENT_ACTIVITY.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, self._render(now))
        return path

    def _atomic_write(self, path: Path, content: str) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)

    def _render(self, now: datetime) -> str:
        active = self.repo.list_active_runs()
        queue = self.repo.list_review_queue()
        recent = self.repo.list_recent_runs(limit=8)
        blocked = self.repo.list_blocked_jobs()
        waiting_jobs = self.repo.list_waiting_jobs()
        stale_seconds = int(self.activity_config.get("heartbeat_stale_seconds", 120))
        stale = self.repo.list_stale_runs(stale_seconds)
        lines = [
            "# Agent activity",
            "",
            f"_Updated: {now.isoformat()}_",
            "",
            "## Working now",
            "",
        ]
        if not active:
            lines.append("_No agents are currently running._")
        else:
            for run in active:
                elapsed = self._elapsed(run["started_at"], run.get("ended_at"), now)
                budget = self.repo.list_budget_usage(run["id"])
                budget_text = (
                    ", ".join(f"{b['budget_name']}={b['amount']}" for b in budget) or "none"
                )
                model = run.get("resolved_model_id") or run.get("model_profile") or "unknown"
                last_update = run.get("last_result_summary") or "in progress"
                lines.append(
                    f"- **{run['role'].title()}** `{run['id']}` is working on "
                    f"[[{run['node_scope']}]] — {run.get('task_label') or 'Investigating'}. "
                    f"Model: {model}. Elapsed: {elapsed}. Budget: {budget_text}. "
                    f"Last update: {last_update}."
                )
        lines.extend(["", "## Waiting / review queue", ""])
        if not queue and not waiting_jobs:
            lines.append("_Review queue is empty._")
        else:
            for item in queue:
                lines.append(
                    f"- Report [[03_reports/{item['report_id']}|{item['report_id']}]] "
                    f"from worker `{item['worker_run_id']}` is waiting for review."
                )
            for job in waiting_jobs:
                lines.append(
                    f"- Job `{job['id']}` on [[{job['node_id']}]] "
                    f"is waiting with status {job['status']}."
                )
        lines.extend(["", "## Needs human", ""])
        needs_human = self.repo.list_needs_human_reports()
        if not needs_human:
            lines.append("_No reports are waiting on a human decision._")
        else:
            for report in needs_human:
                lines.append(
                    f"- Report [[03_reports/{report.id}|{report.id}]] on "
                    f"[[{report.subject_node_id}]] needs a human ACCEPT/REJECT "
                    f"(`resolve_needs_human`)."
                )
        lines.extend(["", "## Recently finished", ""])
        if not recent:
            lines.append("_No completed runs yet._")
        else:
            for run in recent:
                duration = self._elapsed(run["started_at"], run.get("ended_at"), now)
                budget = self.repo.list_budget_usage(run["id"])
                cost = sum(float(b["amount"]) for b in budget)
                model = run.get("resolved_model_id") or run.get("model_profile") or "unknown"
                report = self.repo.get_report_for_run(run["id"])
                report_link = (
                    f" Report: [[03_reports/{report.id}|{report.id}]]."
                    if report is not None
                    else ""
                )
                accepted = ""
                if report is not None:
                    decision = self.repo.get_latest_decision(report.id)
                    if decision and decision.transaction_id:
                        accepted = f" Accepted tx: `{decision.transaction_id}`."
                lines.append(
                    f"- **{run['role'].title()}** `{run['id']}` finished as **{run['status']}** "
                    f"in {duration}. Model: {model}. Budget use: {cost:.1f}.{report_link}"
                    f"{accepted} "
                    f"{run.get('last_result_summary') or run.get('error_message') or ''}"
                )
        lines.extend(["", "## Problems", ""])
        problems: list[str] = []
        failures = [r for r in recent if r["status"] == "FAILED"]
        for run in failures:
            msg = run.get("error_message") or "see run log"
            problems.append(
                f"- `{run['id']}` failed: {run.get('error_code')} — {msg}. "
                "Next action: inspect report or retry dispatch."
            )
        for job in blocked:
            problems.append(
                f"- Job `{job['id']}` on [[{job['node_id']}]] failed/cancelled "
                f"with status {job['status']}."
            )
        for run in stale:
            problems.append(
                f"- `{run['id']}` looks stale (no heartbeat for {stale_seconds}s). "
                "Operator action: inspect run log or cancel/retry."
            )
        if not problems:
            lines.append("_No recent failures or stale agents._")
        else:
            lines.extend(problems)
        lines.append("")
        return "\n".join(lines)

    def _elapsed(self, started_at: str, ended_at: str | None, now: datetime) -> str:
        start = datetime.fromisoformat(started_at)
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if ended_at:
            end = datetime.fromisoformat(ended_at)
            if end.tzinfo is None:
                end = end.replace(tzinfo=UTC)
        else:
            end = now
        delta = end - start
        minutes = int(delta.total_seconds() // 60)
        seconds = int(delta.total_seconds() % 60)
        return f"{minutes}m {seconds:02d}s"

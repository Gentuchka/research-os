"""Human-readable Obsidian activity dashboard."""

from __future__ import annotations

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
        path.write_text(self._render(now), encoding="utf-8")
        return path

    def _render(self, now: datetime) -> str:
        active = self.repo.list_active_runs()
        queue = self.repo.list_review_queue()
        recent = self.repo.list_recent_runs(limit=8)
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
                elapsed = self._elapsed(run["started_at"], now)
                last_update = run.get("last_result_summary") or "in progress"
                lines.append(
                    f"- **{run['role'].title()}** `{run['id']}` is working on "
                    f"[[{run['node_scope']}]] — {run.get('task_label') or 'Investigating'}. "
                    f"Elapsed: {elapsed}. Last update: {last_update}."
                )
        lines.extend(["", "## Waiting / review queue", ""])
        if not queue:
            lines.append("_Review queue is empty._")
        else:
            for item in queue:
                lines.append(
                    f"- Report [[{item['report_id']}]] from worker `{item['worker_run_id']}` "
                    f"is waiting for review."
                )
        lines.extend(["", "## Recently finished", ""])
        if not recent:
            lines.append("_No completed runs yet._")
        else:
            for run in recent:
                lines.append(
                    f"- **{run['role'].title()}** `{run['id']}` finished as **{run['status']}**. "
                    f"{run.get('last_result_summary') or run.get('error_message') or ''}"
                )
        lines.extend(["", "## Problems", ""])
        problems: list[str] = []
        failures = [r for r in recent if r["status"] in {"failed", "FAILED"}]
        for run in failures:
            problems.append(
                f"- `{run['id']}` failed: {run.get('error_code')} — "
                f"{run.get('error_message') or 'see run log'}"
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

    def _elapsed(self, started_at: str, now: datetime) -> str:
        start = datetime.fromisoformat(started_at)
        delta = now - start
        minutes = int(delta.total_seconds() // 60)
        seconds = int(delta.total_seconds() % 60)
        return f"{minutes}m {seconds:02d}s"

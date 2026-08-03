"""Worker runtime with fake or live Cursor SDK backends."""

from __future__ import annotations

import os
from typing import Any

from research_os.agents.worker.cursor_adapter import CursorSdkWorker
from research_os.agents.worker.model_resolver import ModelResolver
from research_os.config import RuntimeConfig
from research_os.kernel.types import RoleContext
from research_os.projection.activity import ActivityProjector
from research_os.reports.intake import ReportIntake
from research_os.store.repository import Repository


class FakeCursorAgent:
    def __init__(self, subject_node_id: str) -> None:
        self.subject_node_id = subject_node_id

    def investigate(self) -> dict[str, Any]:
        return {
            "report_type": "worker",
            "subject_node_id": self.subject_node_id,
            "summary": f"Investigation of {self.subject_node_id}",
            "information_delta": [
                f"Explored implications of {self.subject_node_id}",
            ],
            "claims": [
                {
                    "text": "A specialized variant may reduce the problem to a finite case.",
                    "speculative": True,
                }
            ],
            "proposed_objects": [
                {
                    "type": "Hypothesis",
                    "title": "Finite case variant",
                    "statement": "The conjecture holds for all even integers below 10^6.",
                    "information_gain": "Finite verification target for computational search.",
                }
            ],
            "proposed_links": [
                {
                    "from_id": "$new:0",
                    "to_id": self.subject_node_id,
                    "edge_type": "specializes",
                }
            ],
            "literature_refs": [],
            "estimated_difficulty": 0.6,
            "confidence": 0.4,
        }


class WorkerRuntime:
    def __init__(
        self,
        repo: Repository,
        report_intake: ReportIntake,
        activity: ActivityProjector,
        config: RuntimeConfig,
    ) -> None:
        self.repo = repo
        self.report_intake = report_intake
        self.activity = activity
        self.config = config
        self.model_resolver = ModelResolver(config)
        self.cursor_worker = CursorSdkWorker(repo, report_intake, config, self.model_resolver)

    def run_investigation(self, ctx: RoleContext, subject_node_id: str):
        self.repo.heartbeat_run(ctx.run_id, f"Reading context for {subject_node_id}")
        self.repo.conn.commit()
        self.activity.project_dashboard()
        if os.environ.get("CURSOR_API_KEY") and os.environ.get("RESEARCH_OS_USE_LIVE_SDK") == "1":
            report = self.cursor_worker.investigate(ctx, subject_node_id)
        else:
            payload = FakeCursorAgent(subject_node_id).investigate()
            self.repo.heartbeat_run(ctx.run_id, "Drafting structured report")
            self.repo.conn.commit()
            self.activity.project_dashboard()
            report = self.report_intake.submit(ctx, payload)
        return report

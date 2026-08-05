"""Thinker runtime: global synthesis across the frontier (P3.2).

Unlike the Worker (which investigates a single node), the Thinker looks
across multiple frontier nodes and proposes cross-cutting links/hypotheses.
It reuses the exact same `ReportIntake` -> `ReviewerService.review_report`
pipeline as the Worker (schema already supports `report_type: "thinker"`),
so no new acceptance path is introduced — the Reviewer still makes every
accept/reject call.
"""

from __future__ import annotations

from typing import Any

from research_os.config import RuntimeConfig
from research_os.kernel.types import RoleContext
from research_os.metrics.engine import MetricsEngine
from research_os.projection.activity import ActivityProjector
from research_os.reports.intake import ReportIntake
from research_os.store.repository import Repository


class FakeThinkerAgent:
    """Deterministic offline stand-in for a live cross-node synthesis model."""

    def __init__(self, primary_id: str, secondary_id: str | None) -> None:
        self.primary_id = primary_id
        self.secondary_id = secondary_id

    def synthesize(self) -> dict[str, Any]:
        if self.secondary_id is None:
            return {
                "report_type": "thinker",
                "subject_node_id": self.primary_id,
                "summary": f"Global synthesis pass touching {self.primary_id}",
                "information_delta": [
                    f"Considered {self.primary_id} in isolation; no cross-links found yet."
                ],
                "claims": [
                    {
                        "id": "claim_thinker_0",
                        "text": "No other active frontier node was available for cross-synthesis.",
                        "speculative": True,
                    }
                ],
                "literature_refs": [],
                "estimated_difficulty": 0.5,
                "confidence": 0.3,
            }
        return {
            "report_type": "thinker",
            "subject_node_id": self.primary_id,
            "summary": f"Cross-synthesis between {self.primary_id} and {self.secondary_id}",
            "information_delta": [
                f"Explored a structural relationship between {self.primary_id} "
                f"and {self.secondary_id}",
            ],
            "claims": [
                {
                    "id": "claim_thinker_0",
                    "text": (
                        f"{self.primary_id} and {self.secondary_id} may share a common "
                        "reduction technique."
                    ),
                    "speculative": True,
                }
            ],
            "proposed_objects": [
                {
                    "type": "Hypothesis",
                    "title": "Cross-node reduction hypothesis",
                    "statement": (
                        f"A technique proving progress on {self.primary_id} generalizes "
                        f"to {self.secondary_id}."
                    ),
                    "information_gain": "Links two independently-explored frontier branches.",
                    "claim_index": 0,
                }
            ],
            "proposed_links": [
                {
                    "from_id": "$new:0",
                    "to_id": self.primary_id,
                    "edge_type": "generalizes",
                },
                {
                    "from_id": "$new:0",
                    "to_id": self.secondary_id,
                    "edge_type": "generalizes",
                },
            ],
            "literature_refs": [],
            "estimated_difficulty": 0.6,
            "confidence": 0.35,
        }


class ThinkerRuntime:
    def __init__(
        self,
        repo: Repository,
        report_intake: ReportIntake,
        activity: ActivityProjector,
        metrics: MetricsEngine,
        config: RuntimeConfig,
    ) -> None:
        self.repo = repo
        self.report_intake = report_intake
        self.activity = activity
        self.metrics = metrics
        self.config = config

    def pick_synthesis_targets(self) -> tuple[str, str | None] | None:
        frontier = self.metrics.ranked_frontier(limit=5)
        if not frontier:
            return None
        primary = frontier[0]["id"]
        secondary = frontier[1]["id"] if len(frontier) > 1 else None
        return primary, secondary

    def run_synthesis(self, ctx: RoleContext):
        targets = self.pick_synthesis_targets()
        if targets is None:
            return None
        primary_id, secondary_id = targets
        self.repo.heartbeat_run(ctx.run_id, f"Synthesizing across {primary_id}")
        self.repo.conn.commit()
        self.activity.project_dashboard()
        payload = FakeThinkerAgent(primary_id, secondary_id).synthesize()
        self.repo.heartbeat_run(ctx.run_id, "Drafting thinker report")
        self.repo.conn.commit()
        self.activity.project_dashboard()
        return self.report_intake.submit(ctx, payload)

"""Optional non-blocking advisory pass for the Reviewer (P4.5).

Deterministic anti-slop remains authoritative for every accept/reject
decision. This advisor only appends advisory notes to `agent_events`; it can
never mutate the knowledge graph and never blocks or overrides acceptance.

Enable/disable via `configs/models.yaml` -> `roles.reviewer.llm.enabled`.
`FakeReviewerAdvisor` is a deterministic, offline stand-in used whenever a
live model backend is not wired up (which is the case for the Reviewer role
in this repo); it exists so the advisory pipeline is testable without any
network access.
"""

from __future__ import annotations

from typing import Any, Protocol


class ReviewerAdvisor(Protocol):
    def advise(self, payload: dict[str, Any]) -> list[str]: ...


class NullAdvisor:
    """Used when advisory review is disabled in config."""

    def advise(self, payload: dict[str, Any]) -> list[str]:
        return []


class FakeReviewerAdvisor:
    """Deterministic offline advisory heuristics.

    These are intentionally simple, structural checks (claim count, missing
    evidence on speculative claims) — they are advisory hints for a human,
    not a correctness check, and never affect the deterministic decision.
    """

    def advise(self, payload: dict[str, Any]) -> list[str]:
        notes: list[str] = []
        claims = payload.get("claims", [])
        if len(claims) > 5:
            notes.append(
                f"High claim count ({len(claims)}) in a single report; "
                "consider splitting future investigations."
            )
        for claim in claims:
            if claim.get("speculative") and not claim.get("evidence_refs"):
                text = str(claim.get("text", ""))[:80]
                notes.append(f"Speculative claim without supporting evidence: {text}")
        if not payload.get("literature_refs") and payload.get("report_type") == "worker":
            notes.append("No literature references cited; verify related work was checked.")
        return notes


def build_advisor(models_config: dict[str, Any] | None) -> ReviewerAdvisor:
    reviewer_cfg = (models_config or {}).get("roles", {}).get("reviewer", {})
    llm_cfg = reviewer_cfg.get("llm", {}) if isinstance(reviewer_cfg, dict) else {}
    if isinstance(llm_cfg, dict) and llm_cfg.get("enabled"):
        return FakeReviewerAdvisor()
    return NullAdvisor()

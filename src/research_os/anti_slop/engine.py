"""Deterministic anti-slop checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research_os.anti_slop.embedding import build_similarity_backend
from research_os.anti_slop.similarity import SimilarityBackend
from research_os.kernel.types import canonical_content_hash
from research_os.store.repository import Repository


@dataclass(frozen=True)
class SlopFinding:
    code: str
    message: str
    claim_index: int | None = None


class AntiSlopEngine:
    def __init__(
        self,
        repo: Repository,
        config: dict[str, Any],
        similarity: SimilarityBackend | None = None,
    ) -> None:
        self.repo = repo
        self.config = config
        self.similarity = similarity or build_similarity_backend(config)

    def check_report(self, payload: dict[str, Any], *, run_id: str) -> list[SlopFinding]:
        findings: list[SlopFinding] = []
        min_delta = int(self.config.get("min_information_delta_items", 1))
        delta_items = payload.get("information_delta", [])
        if len(delta_items) < min_delta:
            findings.append(
                SlopFinding("SLOP_LOW_INFORMATION", "information_delta below minimum")
            )
        elif all(len(str(item).strip()) < 12 for item in delta_items):
            findings.append(
                SlopFinding("SLOP_LOW_INFORMATION", "information_delta too vague")
            )

        for idx, claim in enumerate(payload.get("claims", [])):
            if not claim.get("speculative") and not claim.get("evidence_refs"):
                findings.append(
                    SlopFinding(
                        "SLOP_UNSUPPORTED_CLAIM",
                        f"Unsupported claim: {claim.get('text', '')[:80]}",
                        claim_index=idx,
                    )
                )
            for ref in claim.get("evidence_refs", []):
                if not self.repo.object_exists(ref):
                    findings.append(
                        SlopFinding(
                            "SLOP_UNSUPPORTED_CLAIM",
                            f"Unknown evidence ref: {ref}",
                            claim_index=idx,
                        )
                    )

        for ref in payload.get("literature_refs", []):
            if not self.repo.literature_exists(ref):
                findings.append(
                    SlopFinding("SLOP_HALLUCINATED_REF", f"Unknown literature ref: {ref}")
                )

        subject = payload["subject_node_id"]
        prior = self.repo.list_reports_for_node(subject)
        delta_key = "|".join(sorted(payload.get("information_delta", [])))
        attempt_key = payload.get("attempt_key") or delta_key
        for old in prior:
            if old.run_id == run_id:
                continue
            old_delta = "|".join(sorted(old.payload.get("information_delta", [])))
            old_attempt = old.payload.get("attempt_key") or old_delta
            if old_delta == delta_key or old_attempt == attempt_key:
                findings.append(
                    SlopFinding("SLOP_DUPLICATE_REASONING", "Duplicate information_delta")
                )
                break

        for proposed in payload.get("proposed_objects", []):
            content_hash = canonical_content_hash(
                {
                    "type": proposed["type"],
                    "title": proposed["title"],
                    "statement": proposed["statement"],
                    "formalization": None,
                }
            )
            if self.repo.content_hash_exists(content_hash):
                findings.append(
                    SlopFinding("SLOP_REPETITIVE_HYP", "Proposed object duplicates existing")
                )
            threshold = float(self.config.get("semantic_similarity_threshold", 0.92))
            for obj in self.repo.list_objects(limit=500):
                if self.similarity.score(proposed["statement"], obj.statement) >= threshold:
                    findings.append(
                        SlopFinding(
                            "SLOP_COSMETIC_VARIANT",
                            f"Cosmetic variant of {obj.id}",
                        )
                    )
                    break

        if payload.get("proposes_status_change"):
            findings.append(
                SlopFinding("SLOP_SCOPE_VIOLATION", "Report proposes direct status change")
            )

        return findings

    def claim_findings(self, findings: list[SlopFinding], claim_index: int) -> list[SlopFinding]:
        return [f for f in findings if f.claim_index == claim_index]

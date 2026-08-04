"""Pluggable semantic similarity for anti-slop checks."""

from __future__ import annotations

from typing import Protocol

from research_os.anti_slop.normalize import token_jaccard


class SimilarityBackend(Protocol):
    def score(self, left: str, right: str) -> float: ...


class TokenJaccardSimilarity:
    def score(self, left: str, right: str) -> float:
        return token_jaccard(left, right)

"""Deterministic, offline, local embedding-based similarity backend.

This is P3.4 ("embedding-backed anti-slop"). It replaces plain token-Jaccard
with a hashed character n-gram bag-of-features embedding so that paraphrased
duplicate claims/hypotheses (different words, same meaning) score as similar,
not just exact token overlaps.

Deliberately does NOT call any external API or model — fully offline and
reproducible, so CI and anti-slop tests never depend on network access.
Config-driven: `configs/anti_slop.yaml` -> `similarity_backend` selects between
`token_jaccard` (legacy) and `hashing_embedding` (default).
"""

from __future__ import annotations

import math
import re
from hashlib import sha1
from typing import Any

from research_os.anti_slop.similarity import SimilarityBackend, TokenJaccardSimilarity

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NGRAM_SIZE = 3
_VECTOR_DIM = 256


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _char_ngrams(token: str, n: int = _NGRAM_SIZE) -> list[str]:
    if len(token) <= n:
        return [token]
    return [token[i : i + n] for i in range(len(token) - n + 1)]


def _bucket(gram: str, dim: int) -> int:
    return int(sha1(gram.encode("utf-8")).hexdigest(), 16) % dim


def embed(text: str, dim: int = _VECTOR_DIM) -> list[float]:
    """Deterministic hashed bag-of-char-ngrams embedding (offline, no model)."""
    vector = [0.0] * dim
    for token in _tokens(text):
        for gram in _char_ngrams(token):
            vector[_bucket(gram, dim)] += 1.0
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        return vector
    return [v / norm for v in vector]


def cosine(a: list[float], b: list[float]) -> float:
    score = sum(x * y for x, y in zip(a, b, strict=True))
    return max(0.0, min(1.0, score))


class HashingEmbeddingSimilarity:
    """Local hashed-embedding similarity backend.

    Approximates semantic closeness via hashed character n-gram vectors,
    catching paraphrases that token-Jaccard misses without requiring network
    access or an external embedding API.
    """

    def score(self, left: str, right: str) -> float:
        return cosine(embed(left), embed(right))


def build_similarity_backend(config: dict[str, Any] | None) -> SimilarityBackend:
    name = (config or {}).get("similarity_backend", "hashing_embedding")
    if name == "token_jaccard":
        return TokenJaccardSimilarity()
    return HashingEmbeddingSimilarity()

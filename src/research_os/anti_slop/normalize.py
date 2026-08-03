"""Text normalization for anti-slop checks."""

from __future__ import annotations

import re


def normalize_statement(text: str) -> str:
    lowered = text.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^\w\s>.=+-]", "", lowered)
    return lowered


def token_jaccard(a: str, b: str) -> float:
    ta = set(normalize_statement(a).split())
    tb = set(normalize_statement(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)

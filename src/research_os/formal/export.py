"""Formal export scaffold (P6).

Produces human-readable *stub* text in Lean-like syntax for a research
object's statement. This is intentionally NOT a real formalization and is
never compiled, type-checked, or used to verify anything — it exists purely
so a human/reviewer can copy a starting point into a real prover. No
verification status is attached to any object as a result of exporting.
"""

from __future__ import annotations

from typing import Any


def export_lean_stub(obj: dict[str, Any]) -> str:
    title = obj.get("title", "untitled")
    statement = obj.get("statement", "")
    formalization = obj.get("formalization")
    lines = [
        f"-- Auto-generated stub for {obj.get('id', 'unknown')} ({title})",
        "-- NOT VERIFIED. This is a drafting aid only; the Reviewer's judgment",
        "-- (not a compiler or prover) is what determines acceptance.",
        "",
    ]
    if formalization:
        lines.append(formalization)
    else:
        lines.append(f"theorem {_slug(title)} : sorry := by")
        lines.append(f"  -- statement: {statement}")
        lines.append("  sorry")
    return "\n".join(lines)


def _slug(title: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in title.lower()).strip("_") or "goal"


def export_formal(obj: dict[str, Any], fmt: str = "lean") -> str:
    if fmt == "lean":
        return export_lean_stub(obj)
    raise ValueError(f"Unsupported formal export format: {fmt}")

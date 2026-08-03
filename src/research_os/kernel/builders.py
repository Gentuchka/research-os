"""Object construction helpers."""

from __future__ import annotations

from research_os.kernel.types import (
    Provenance,
    ResearchObject,
    canonical_content_hash,
    new_id,
    utc_now,
)


def build_object(
    *,
    object_type: str,
    title: str,
    statement: str,
    origin_kind: str,
    origin_refs: list[str],
    run_id: str,
    status: str = "ACTIVE",
    information_gain: str,
    formalization: str | None = None,
    evidence_refs: list[str] | None = None,
    object_id: str | None = None,
) -> ResearchObject:
    now = utc_now().isoformat()
    payload = {
        "type": object_type,
        "title": title,
        "statement": statement,
        "formalization": formalization,
    }
    return ResearchObject(
        id=object_id or new_id(object_type),
        type=object_type,
        title=title,
        statement=statement,
        formalization=formalization,
        status=status,
        created_at=now,
        admitted_at=now,
        content_hash=canonical_content_hash(payload),
        provenance=Provenance(
            origin_kind=origin_kind,
            origin_refs=origin_refs,
            created_by_run=run_id,
        ),
        evidence_refs=evidence_refs or [],
        information_gain=information_gain,
    )

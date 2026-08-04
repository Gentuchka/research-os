"""Transaction operation serialization helpers."""

from __future__ import annotations

from typing import Any

from research_os.kernel.types import (
    AppendMetricOp,
    AppendNodeOp,
    ArchiveNodeOp,
    CreateLinkOp,
    MergeEquivalenceClassOp,
    Operation,
    Provenance,
    ResearchObject,
    SetStatusOp,
    SupersedeNodeOp,
    canonical_content_hash,
)


def parse_object(data: dict[str, Any]) -> ResearchObject:
    prov = data["provenance"]
    payload = {
        "type": data["type"],
        "title": data["title"],
        "statement": data["statement"],
        "formalization": data.get("formalization"),
    }
    return ResearchObject(
        id=data["id"],
        type=data["type"],
        title=data["title"],
        statement=data["statement"],
        formalization=data.get("formalization"),
        status=data.get("status", "ACTIVE"),
        created_at=data["created_at"],
        admitted_at=data.get("admitted_at"),
        content_hash=data.get("content_hash") or canonical_content_hash(payload),
        provenance=Provenance(
            origin_kind=prov["origin_kind"],
            origin_refs=prov["origin_refs"],
            created_by_run=prov["created_by_run"],
        ),
        evidence_refs=data.get("evidence_refs", []),
        tags=data.get("tags", []),
        information_gain=data.get("information_gain"),
    )


def parse_ops(raw_ops: list[dict[str, Any]]) -> list[Operation]:
    parsed: list[Operation] = []
    for raw in raw_ops:
        op_type = raw["op_type"]
        if op_type == "append_node":
            parsed.append(AppendNodeOp(object=parse_object(raw["object"])))
        elif op_type == "archive_node":
            parsed.append(ArchiveNodeOp(node_id=raw["node_id"], reason=raw["reason"]))
        elif op_type == "supersede_node":
            parsed.append(
                SupersedeNodeOp(old_id=raw["old_id"], new_id=raw["new_id"], reason=raw["reason"])
            )
        elif op_type == "create_link":
            parsed.append(
                CreateLinkOp(
                    from_id=raw["from_id"],
                    to_id=raw["to_id"],
                    edge_type=raw["edge_type"],
                    graph=raw.get("graph", "math"),
                )
            )
        elif op_type == "merge_equivalence_class":
            parsed.append(
                MergeEquivalenceClassOp(
                    representative_id=raw["representative_id"],
                    member_id=raw["member_id"],
                    class_id=raw.get("class_id"),
                )
            )
        elif op_type == "set_status":
            parsed.append(
                SetStatusOp(
                    node_id=raw["node_id"],
                    status=raw["status"],
                    evidence_refs=raw.get("evidence_refs", []),
                    reason=raw["reason"],
                )
            )
        elif op_type == "append_metric":
            parsed.append(
                AppendMetricOp(
                    node_id=raw["node_id"],
                    metric_name=raw["metric_name"],
                    value=float(raw["value"]),
                    method=raw["method"],
                    version=raw["version"],
                )
            )
        else:
            raise ValueError(f"Unknown op_type: {op_type}")
    return parsed

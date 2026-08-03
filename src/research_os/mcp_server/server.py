"""Research OS MCP server."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from research_os.acl import ACL
from research_os.config import RuntimeConfig
from research_os.factory import build_app
from research_os.kernel.types import (
    AgentRole,
    AppendMetricOp,
    AppendNodeOp,
    ArchiveNodeOp,
    CreateLinkOp,
    MergeEquivalenceClassOp,
    Provenance,
    ResearchObject,
    RoleContext,
    SetStatusOp,
    SupersedeNodeOp,
    Transaction,
    canonical_content_hash,
    new_tx_id,
)

mcp = FastMCP("research-os")
_app = None
_acl = None


def _bootstrap(config: RuntimeConfig | None = None):
    global _app, _acl
    if _app is None:
        cfg = config or RuntimeConfig.load()
        _app = build_app(cfg)
        _acl = ACL(cfg.roles_config)
    return _app


def _ctx(role: str, run_id: str, node_scope: str | None = None) -> RoleContext:
    return RoleContext(role=AgentRole(role), run_id=run_id, node_scope=node_scope)


def _guard(ctx: RoleContext, tool_name: str) -> None:
    assert _acl is not None
    _acl.assert_tool(ctx, tool_name)


def _parse_object(data: dict[str, Any]) -> ResearchObject:
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


def _parse_ops(raw_ops: list[dict[str, Any]]) -> list[Any]:
    parsed: list[Any] = []
    for raw in raw_ops:
        op_type = raw["op_type"]
        if op_type == "append_node":
            parsed.append(AppendNodeOp(object=_parse_object(raw["object"])))
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


@mcp.tool()
def get_node(role: str, run_id: str, node_id: str) -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "get_node")
    return json.dumps(app.tx_service.get_node(node_id))


@mcp.tool()
def find_frontier(role: str, run_id: str, limit: int = 20) -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "find_frontier")
    return json.dumps(app.metrics.ranked_frontier(limit))


@mcp.tool()
def graph_statistics(role: str, run_id: str) -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "graph_statistics")
    return json.dumps(app.tx_service.graph_statistics())


@mcp.tool()
def history(role: str, run_id: str, node_id: str) -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "history")
    return json.dumps(app.tx_service.history(node_id))


@mcp.tool()
def submit_report(role: str, run_id: str, report_json: str) -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "submit_report")
    report = app.report_intake.submit(ctx, json.loads(report_json))
    app.activity.project_dashboard(force=True)
    return json.dumps(report.to_dict())


@mcp.tool()
def get_report(role: str, run_id: str, report_id: str) -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "get_node")
    report = app.repo.get_report(report_id)
    return json.dumps(None if report is None else report.to_dict())


@mcp.tool()
def list_pending_reports(role: str, run_id: str) -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "find_frontier")
    return json.dumps([r.to_dict() for r in app.repo.list_pending_reports()])


@mcp.tool()
def review_report(role: str, run_id: str, report_id: str) -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "apply_transaction")
    outcome = app.reviewer.review_report(ctx, report_id)
    return json.dumps(
        {
            "decision": outcome.decision,
            "reason_codes": outcome.reason_codes,
            "accepted": outcome.apply_result.accepted if outcome.apply_result else False,
        }
    )


@mcp.tool()
def compute_metrics(role: str, run_id: str, node_ids_json: str = "[]") -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "compute_metrics")
    node_ids = json.loads(node_ids_json)
    if not node_ids:
        node_ids = [obj.id for obj in app.repo.list_objects(limit=1000)]
    app.metrics.recompute(node_ids)
    app.repo.conn.commit()
    return json.dumps({"recomputed": node_ids})


@mcp.tool()
def dispatch_worker(role: str, run_id: str, node_id: str = "") -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "find_frontier")
    result = app.scheduler.dispatch_next(node_id=node_id or None)
    return json.dumps(result)


@mcp.tool()
def get_activity(role: str, run_id: str) -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "graph_statistics")
    path = app.activity.project_dashboard(force=True)
    return json.dumps({"path": str(path), "content": path.read_text(encoding="utf-8")})


@mcp.tool()
def apply_transaction(role: str, run_id: str, transaction_json: str) -> str:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "apply_transaction")
    payload = json.loads(transaction_json)
    tx = Transaction(
        id=payload.get("id") or new_tx_id(),
        actor_role=role,
        actor_run_id=run_id,
        summary=payload["summary"],
        ops=_parse_ops(payload["ops"]),
        created_at=payload.get("created_at", ""),
    )
    result = app.tx_service.apply(ctx, tx)
    app.activity.project_dashboard(force=True)
    return json.dumps(
        {
            "tx_id": result.tx_id,
            "accepted": result.accepted,
            "rejections": result.rejections,
            "affected_node_ids": result.affected_node_ids,
            "git_commit_sha": result.git_commit_sha,
            "projection_status": result.projection_status,
        }
    )


def create_service(config: RuntimeConfig | None = None):
    return _bootstrap(config).tx_service


def main() -> None:
    _bootstrap()
    mcp.run()


if __name__ == "__main__":
    main()

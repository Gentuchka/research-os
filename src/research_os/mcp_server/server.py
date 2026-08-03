"""Research OS MCP server."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from research_os.acl import ACL
from research_os.config import RuntimeConfig
from research_os.factory import build_service
from research_os.kernel.transaction_service import TransactionService
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
from research_os.store.repository import Repository

mcp = FastMCP("research-os")
_config: RuntimeConfig | None = None
_repo: Repository | None = None
_service: TransactionService | None = None
_acl: ACL | None = None


def _bootstrap(config: RuntimeConfig | None = None) -> None:
    global _config, _repo, _service, _acl
    if _service is not None:
        return
    _config = config or RuntimeConfig.load()
    _service = build_service(_config)
    _repo = _service.repo
    _acl = ACL(_config.roles_config)


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
    """Fetch a research object by ID."""
    _bootstrap()
    assert _service is not None
    ctx = _ctx(role, run_id)
    _guard(ctx, "get_node")
    result = _service.get_node(node_id)
    return json.dumps(result)


@mcp.tool()
def find_frontier(role: str, run_id: str, limit: int = 20) -> str:
    """Return ACTIVE frontier nodes."""
    _bootstrap()
    assert _service is not None
    ctx = _ctx(role, run_id)
    _guard(ctx, "find_frontier")
    return json.dumps(_service.find_frontier(limit))


@mcp.tool()
def graph_statistics(role: str, run_id: str) -> str:
    """Return graph counts and distributions."""
    _bootstrap()
    assert _service is not None
    ctx = _ctx(role, run_id)
    _guard(ctx, "graph_statistics")
    return json.dumps(_service.graph_statistics())


@mcp.tool()
def history(role: str, run_id: str, node_id: str) -> str:
    """Return append-only event history for a node."""
    _bootstrap()
    assert _service is not None
    ctx = _ctx(role, run_id)
    _guard(ctx, "history")
    return json.dumps(_service.history(node_id))


@mcp.tool()
def apply_transaction(role: str, run_id: str, transaction_json: str) -> str:
    """Apply a validated transaction (Reviewer/Human only)."""
    _bootstrap()
    assert _service is not None
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
    result = _service.apply(ctx, tx)
    return json.dumps(
        {
            "tx_id": result.tx_id,
            "accepted": result.accepted,
            "rejections": result.rejections,
            "affected_node_ids": result.affected_node_ids,
            "git_commit_sha": result.git_commit_sha,
        }
    )


def create_service(config: RuntimeConfig | None = None) -> TransactionService:
    """Programmatic entrypoint for scripts."""
    cfg = config or RuntimeConfig.load()
    return build_service(cfg)


def main() -> None:
    _bootstrap()
    mcp.run()


if __name__ == "__main__":
    main()

"""Research OS MCP server."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from research_os.acl import ACL
from research_os.config import RuntimeConfig
from research_os.factory import build_app
from research_os.kernel.serialization import parse_ops
from research_os.kernel.types import (
    AgentRole,
    InvariantCode,
    KernelError,
    RoleContext,
    Transaction,
    new_tx_id,
)
from research_os.mcp_server.models import (
    ActivityResult,
    ApplyTransactionResult,
    CancelRunResult,
    ComputeMetricsResult,
    ConsumeBudgetResult,
    DispatchWorkerResult,
    ReviewReportResult,
    SubmitReportResult,
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
    app = _bootstrap()
    authoritative = app.repo.get_run_role(run_id)
    if authoritative is not None and authoritative != role:
        raise KernelError(
            InvariantCode.ACL_DENIED,
            f"run_id {run_id} is bound to role {authoritative}, not {role}",
        )
    return RoleContext(role=AgentRole(role), run_id=run_id, node_scope=node_scope)


def _guard(ctx: RoleContext, tool_name: str) -> None:
    assert _acl is not None
    _acl.assert_tool(ctx, tool_name)


@mcp.tool()
def get_node(role: str, run_id: str, node_id: str) -> dict[str, Any]:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "get_node")
    return app.tx_service.get_node(node_id) or {}


@mcp.tool()
def find_frontier(role: str, run_id: str, limit: int = 20) -> list[dict[str, Any]]:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "find_frontier")
    return app.metrics.ranked_frontier(limit)


@mcp.tool()
def graph_statistics(role: str, run_id: str) -> dict[str, Any]:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "graph_statistics")
    return app.tx_service.graph_statistics()


@mcp.tool()
def history(role: str, run_id: str, node_id: str) -> list[dict[str, Any]]:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "history")
    return app.tx_service.history(node_id)


@mcp.tool()
def submit_report(role: str, run_id: str, report: dict[str, Any]) -> SubmitReportResult:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "submit_report")
    report_obj = app.report_intake.submit(ctx, report)
    app.activity.project_dashboard(force=True)
    return SubmitReportResult(**report_obj.to_dict())


@mcp.tool()
def get_report(role: str, run_id: str, report_id: str) -> dict[str, Any] | None:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "get_report")
    report = app.repo.get_report(report_id)
    return None if report is None else report.to_dict()


@mcp.tool()
def list_pending_reports(role: str, run_id: str) -> list[dict[str, Any]]:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "list_pending_reports")
    return [r.to_dict() for r in app.repo.list_pending_reports()]


@mcp.tool()
def review_report(role: str, run_id: str, report_id: str) -> ReviewReportResult:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "review_report")
    outcome = app.reviewer.review_report(ctx, report_id)
    return ReviewReportResult(
        decision=outcome.decision,
        reason_codes=outcome.reason_codes,
        accepted=outcome.apply_result.accepted if outcome.apply_result else False,
        accepted_claim_indices=outcome.accepted_claim_indices or [],
        rejected_claim_indices=outcome.rejected_claim_indices or [],
    )


@mcp.tool()
def compute_metrics(
    role: str, run_id: str, node_ids: list[str] | None = None
) -> ComputeMetricsResult:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "compute_metrics")
    ids = node_ids or [obj.id for obj in app.repo.list_objects(limit=1000)]
    app.metrics.recompute(ids)
    app.repo.conn.commit()
    return ComputeMetricsResult(recomputed=ids)


@mcp.tool()
def dispatch_worker(role: str, run_id: str, node_id: str = "") -> DispatchWorkerResult:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "dispatch_worker")
    result = app.scheduler.dispatch_next(node_id=node_id or None)
    return DispatchWorkerResult(**result)


@mcp.tool()
def get_activity(role: str, run_id: str) -> ActivityResult:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "get_activity")
    path = app.activity.project_dashboard(force=True)
    return ActivityResult(path=str(path), content=path.read_text(encoding="utf-8"))


@mcp.tool()
def consume_budget(
    role: str,
    run_id: str,
    node_id: str,
    budget_name: str,
    amount: float = 1.0,
) -> ConsumeBudgetResult:
    app = _bootstrap()
    ctx = _ctx(role, run_id, node_scope=node_id)
    _guard(ctx, "consume_budget")
    result = app.budgets.consume(
        run_id=run_id,
        node_id=node_id,
        budget_name=budget_name,
        amount=amount,
    )
    app.repo.conn.commit()
    return ConsumeBudgetResult(**result)


@mcp.tool()
def cancel_run(
    role: str, run_id: str, target_run_id: str, reason: str = ""
) -> CancelRunResult:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "cancel_run")
    result = app.scheduler.cancel_run(target_run_id, reason or "cancelled by operator")
    return CancelRunResult(**result)


@mcp.tool()
def replay_projection(role: str, run_id: str, tx_id: str) -> ApplyTransactionResult:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "replay_projection")
    result = app.tx_service.replay_projection(tx_id)
    return ApplyTransactionResult(
        tx_id=result.tx_id,
        accepted=result.accepted,
        rejections=result.rejections,
        affected_node_ids=result.affected_node_ids,
        git_commit_sha=result.git_commit_sha,
        projection_status=result.projection_status,
    )


@mcp.tool()
def apply_transaction(
    role: str, run_id: str, transaction: dict[str, Any]
) -> ApplyTransactionResult:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "apply_transaction")
    tx = Transaction(
        id=transaction.get("id") or new_tx_id(),
        actor_role=role,
        actor_run_id=run_id,
        summary=transaction["summary"],
        ops=parse_ops(transaction["ops"]),
        created_at=transaction.get("created_at", ""),
    )
    result = app.tx_service.apply(ctx, tx)
    app.activity.project_dashboard(force=True)
    return ApplyTransactionResult(
        tx_id=result.tx_id,
        accepted=result.accepted,
        rejections=result.rejections,
        affected_node_ids=result.affected_node_ids,
        git_commit_sha=result.git_commit_sha,
        projection_status=result.projection_status,
    )


def create_service(config: RuntimeConfig | None = None):
    return _bootstrap(config).tx_service


def main() -> None:
    _bootstrap()
    mcp.run()


if __name__ == "__main__":
    main()

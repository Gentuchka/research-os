"""Research OS MCP server."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from research_os.acl import ACL
from research_os.anti_slop.embedding import cosine, embed
from research_os.config import RuntimeConfig
from research_os.factory import build_app
from research_os.formal.export import export_formal as _render_formal_export
from research_os.kernel.builders import build_object
from research_os.kernel.serialization import parse_ops
from research_os.kernel.types import (
    AgentRole,
    AppendNodeOp,
    InvariantCode,
    KernelError,
    MergeEquivalenceClassOp,
    RoleContext,
    SetStatusOp,
    Transaction,
    new_tx_id,
)
from research_os.mcp_server.models import (
    ActivityResult,
    ApplyTransactionResult,
    CancelRunResult,
    ComputeMetricsResult,
    ConsumeBudgetResult,
    DispatchThinkerResult,
    DispatchWorkerResult,
    ExportFormalResult,
    FindDuplicateResult,
    InjectLiteratureResult,
    MergeDuplicateResult,
    NearestMainResult,
    OverrideBudgetResult,
    PinNodeResult,
    ReviewReportResult,
    SetStatusResult,
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
def dispatch_thinker(role: str, run_id: str) -> DispatchThinkerResult:
    """Dispatch a global synthesis pass across the frontier (P3.2)."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "dispatch_thinker")
    result = app.scheduler.dispatch_thinker()
    return DispatchThinkerResult(**result)


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


def _apply_status(app, ctx: RoleContext, node_id: str, status: str, reason: str) -> None:
    tx = Transaction(
        id=new_tx_id(),
        actor_role=ctx.role.value,
        actor_run_id=ctx.run_id,
        summary=f"Set {node_id} status to {status}: {reason}",
        ops=[SetStatusOp(node_id=node_id, status=status, evidence_refs=[], reason=reason)],
    )
    result = app.tx_service.apply(ctx, tx)
    if not result.accepted:
        raise KernelError(InvariantCode.INVALID_OPERATION, str(result.rejections))
    app.activity.project_dashboard(force=True)


@mcp.tool()
def pin_node(role: str, run_id: str, node_id: str, weight: float = 1.0) -> PinNodeResult:
    """Human priority pin (P3.1). Biases frontier ranking only; does not
    mutate the knowledge graph or affect proof/counterexample acceptance."""
    app = _bootstrap()
    ctx = _ctx(role, run_id, node_scope=node_id)
    _guard(ctx, "pin_node")
    app.metrics.set_human_pin(node_id, weight)
    app.repo.conn.commit()
    return PinNodeResult(node_id=node_id, weight=weight)


@mcp.tool()
def freeze_node(role: str, run_id: str, node_id: str, reason: str = "") -> SetStatusResult:
    """Human freeze (P3.1): pause a node without discarding it (ACTIVE -> FROZEN)."""
    app = _bootstrap()
    ctx = _ctx(role, run_id, node_scope=node_id)
    _guard(ctx, "freeze_node")
    _apply_status(app, ctx, node_id, "FROZEN", reason or "frozen by operator")
    return SetStatusResult(node_id=node_id, status="FROZEN", reason=reason)


@mcp.tool()
def unfreeze_node(role: str, run_id: str, node_id: str, reason: str = "") -> SetStatusResult:
    """Human unfreeze (P3.1): resume a frozen or stuck node (-> ACTIVE)."""
    app = _bootstrap()
    ctx = _ctx(role, run_id, node_scope=node_id)
    _guard(ctx, "unfreeze_node")
    _apply_status(app, ctx, node_id, "ACTIVE", reason or "unfrozen by operator")
    return SetStatusResult(node_id=node_id, status="ACTIVE", reason=reason)


@mcp.tool()
def inject_literature(
    role: str,
    run_id: str,
    title: str,
    statement: str,
    information_gain: str,
    object_type: str = "Paper",
) -> InjectLiteratureResult:
    """Human literature injection (P3.1): admit an externally-known result
    (paper/definition/technique) directly, bypassing worker investigation."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "inject_literature")
    obj = build_object(
        object_type=object_type,
        title=title,
        statement=statement,
        origin_kind="human_directive",
        origin_refs=["bootstrap"],
        run_id=ctx.run_id,
        information_gain=information_gain,
    )
    tx = Transaction(
        id=new_tx_id(),
        actor_role=ctx.role.value,
        actor_run_id=ctx.run_id,
        summary=f"Inject literature: {title}",
        ops=[AppendNodeOp(object=obj)],
    )
    result = app.tx_service.apply(ctx, tx)
    if not result.accepted:
        raise KernelError(InvariantCode.INVALID_OPERATION, str(result.rejections))
    app.activity.project_dashboard(force=True)
    return InjectLiteratureResult(node_id=obj.id, title=title)


@mcp.tool()
def override_budget(
    role: str, run_id: str, node_id: str, budget_name: str, new_limit: float
) -> OverrideBudgetResult:
    """Human budget override (P3.1): raise/lower a node's budget ceiling."""
    app = _bootstrap()
    ctx = _ctx(role, run_id, node_scope=node_id)
    _guard(ctx, "override_budget")
    result = app.repo.override_budget(node_id, budget_name, new_limit)
    app.repo.conn.commit()
    return OverrideBudgetResult(**result)


@mcp.tool()
def resolve_needs_human(
    role: str, run_id: str, report_id: str, decision: str, note: str = ""
) -> ReviewReportResult:
    """Human resolution of a NEEDS_HUMAN report (P3.5). `decision` is ACCEPT
    or REJECT — this is still a human judgment call, not mechanical verification."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "resolve_needs_human")
    outcome = app.reviewer.human_resolve(ctx, report_id, decision=decision, note=note)
    return ReviewReportResult(
        decision=outcome.decision,
        reason_codes=outcome.reason_codes,
        accepted=outcome.apply_result.accepted if outcome.apply_result else False,
        accepted_claim_indices=outcome.accepted_claim_indices or [],
        rejected_claim_indices=outcome.rejected_claim_indices or [],
    )


@mcp.tool()
def semantic_search(role: str, run_id: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Local hashed-embedding text search over object statements (P4.1).
    Offline/deterministic — no external search API or network access."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "semantic_search")
    query_vec = embed(query)
    scored = [
        (cosine(query_vec, embed(obj.statement)), obj)
        for obj in app.repo.list_objects(limit=10_000)
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [{"score": score, **obj.to_dict()} for score, obj in scored[:limit]]


@mcp.tool()
def find_similar(role: str, run_id: str, node_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Find objects with statements similar to `node_id` (P4.1)."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "find_similar")
    subject = app.repo.get_object(node_id)
    if subject is None:
        return []
    query_vec = embed(subject.statement)
    scored = [
        (cosine(query_vec, embed(obj.statement)), obj)
        for obj in app.repo.list_objects(limit=10_000)
        if obj.id != node_id
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [{"score": score, **obj.to_dict()} for score, obj in scored[:limit]]


@mcp.tool()
def find_orphans(role: str, run_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Objects with no math or provenance edges at all (P4.1)."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "find_orphans")
    edges = app.repo.list_math_edges() + app.repo.list_provenance_edges()
    connected = {a for a, b, _ in edges} | {b for a, b, _ in edges}
    orphans = [obj for obj in app.repo.list_objects(limit=10_000) if obj.id not in connected]
    return [obj.to_dict() for obj in orphans[:limit]]


@mcp.tool()
def find_dead_nodes(role: str, run_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Nodes that are STUCK, SUPERSEDED, or ARCHIVED (P4.1)."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "find_dead_nodes")
    dead_statuses = {"STUCK", "SUPERSEDED", "ARCHIVED"}
    dead = [obj for obj in app.repo.list_objects(limit=10_000) if obj.status in dead_statuses]
    return [obj.to_dict() for obj in dead[:limit]]


@mcp.tool()
def timeline(role: str, run_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Global event timeline across the whole graph (P4.1)."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "timeline")
    return app.repo.list_all_events(limit)


@mcp.tool()
def nearest_main(role: str, run_id: str, node_id: str) -> NearestMainResult:
    """Shortest path from `node_id` to the nearest MainConjecture (P4.1)."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "nearest_main")
    return NearestMainResult(**app.metrics.nearest_main_path(node_id))


def _search_by_type(
    role: str, run_id: str, tool_name: str, object_type: str, query: str, limit: int
) -> list[dict[str, Any]]:
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, tool_name)
    objects = app.repo.list_objects(object_type=object_type, limit=10_000)
    if query:
        needle = query.lower()
        objects = [
            obj
            for obj in objects
            if needle in obj.title.lower() or needle in obj.statement.lower()
        ]
    return [obj.to_dict() for obj in objects[:limit]]


@mcp.tool()
def search_by_definition(
    role: str, run_id: str, query: str = "", limit: int = 10
) -> list[dict[str, Any]]:
    """Search Definition-type objects, optionally filtered by title/statement text (P4.1)."""
    return _search_by_type(role, run_id, "search_by_definition", "Definition", query, limit)


@mcp.tool()
def search_counterexamples(
    role: str, run_id: str, query: str = "", limit: int = 10
) -> list[dict[str, Any]]:
    """Search Counterexample-type objects (P4.1)."""
    return _search_by_type(role, run_id, "search_counterexamples", "Counterexample", query, limit)


@mcp.tool()
def search_techniques(
    role: str, run_id: str, query: str = "", limit: int = 10
) -> list[dict[str, Any]]:
    """Search Technique-type objects (P4.1)."""
    return _search_by_type(role, run_id, "search_techniques", "Technique", query, limit)


@mcp.tool()
def find_duplicate(
    role: str, run_id: str, statement: str, limit: int = 5
) -> list[FindDuplicateResult]:
    """Find existing objects whose statement is likely a duplicate of `statement`
    (P4.4), using the same similarity backend anti-slop uses for review."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "find_duplicate")
    threshold = app.config.anti_slop_config.get("semantic_similarity_threshold", 0.92)
    scored = []
    for obj in app.repo.list_objects(limit=10_000):
        score = app.anti_slop.similarity.score(statement, obj.statement)
        if score >= threshold:
            scored.append(FindDuplicateResult(node_id=obj.id, score=score))
    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:limit]


@mcp.tool()
def merge_duplicate(
    role: str, run_id: str, representative_id: str, member_id: str
) -> MergeDuplicateResult:
    """Merge `member_id` into the equivalence class of `representative_id` (P4.4).
    This is graph bookkeeping only — a human/reviewer decided these are duplicates,
    this tool does not itself judge equivalence."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "merge_duplicate")
    tx = Transaction(
        id=new_tx_id(),
        actor_role=ctx.role.value,
        actor_run_id=ctx.run_id,
        summary=f"Merge {member_id} into equivalence class of {representative_id}",
        ops=[MergeEquivalenceClassOp(representative_id=representative_id, member_id=member_id)],
    )
    result = app.tx_service.apply(ctx, tx)
    app.activity.project_dashboard(force=True)
    return MergeDuplicateResult(
        tx_id=result.tx_id,
        accepted=result.accepted,
        representative_id=representative_id,
        member_id=member_id,
        rejections=result.rejections,
    )


@mcp.tool()
def export_formal(role: str, run_id: str, node_id: str, fmt: str = "lean") -> ExportFormalResult:
    """Export a non-verified formalization stub for a node (P6, scaffold only).
    Never attaches a verification status or gates acceptance in any way."""
    app = _bootstrap()
    ctx = _ctx(role, run_id)
    _guard(ctx, "export_formal")
    obj = app.repo.get_object(node_id)
    if obj is None:
        raise KernelError(InvariantCode.NOT_FOUND, f"Object not found: {node_id}")
    content = _render_formal_export(obj.to_dict(), fmt)
    return ExportFormalResult(node_id=node_id, format=fmt, content=content)


def create_service(config: RuntimeConfig | None = None):
    return _bootstrap(config).tx_service


def main() -> None:
    _bootstrap()
    mcp.run()


if __name__ == "__main__":
    main()

"""Tests for the P3-P7 roadmap implementation.

Constraint under test throughout: proof/counterexample acceptance is always
a Reviewer decision (deterministic anti-slop + claim partitioning, or human
judgment) — nothing here performs numeric/mechanical verification.
"""

from __future__ import annotations

import copy
import dataclasses

import pytest
from conftest import admit_main, load_report_fixture

from research_os.acl import ACL
from research_os.analytics.weekly import WeeklyAnalytics
from research_os.anti_slop.embedding import HashingEmbeddingSimilarity, cosine, embed
from research_os.backup.service import BackupService
from research_os.cli import main as cli_main
from research_os.daemon.scheduler_daemon import SchedulerDaemon
from research_os.kernel.builders import build_object
from research_os.kernel.types import (
    AgentRole,
    AppendNodeOp,
    CreateLinkOp,
    RoleContext,
    SetStatusOp,
    Transaction,
    new_tx_id,
)
from research_os.mcp_server import server as mcp_server


def test_hashing_embedding_similarity_catches_paraphrase():
    backend = HashingEmbeddingSimilarity()
    a = "Every even integer greater than two is the sum of two primes."
    b = "Every even number bigger than two equals the sum of two primes."
    unrelated = "The mitochondria is the powerhouse of the cell."
    assert backend.score(a, b) > backend.score(a, unrelated)


def test_embed_is_deterministic_across_calls():
    text = "A hypothesis about even integers and prime sums."
    assert embed(text) == embed(text)
    assert cosine(embed(text), embed(text)) > 0.99


def test_metrics_v2_computes_real_values(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("accept_hypothesis_with_link.json")
    payload["subject_node_id"] = main_id
    payload["proposed_links"][0]["to_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    outcome = app.reviewer.review_report(reviewer_ctx, report.id)
    assert outcome.decision == "ACCEPT"

    for metric_name in (
        "importance",
        "promise",
        "novelty",
        "information_gain",
        "research_cost",
        "branching_factor",
    ):
        value = app.repo.get_latest_metric(main_id, metric_name)
        assert value is not None, metric_name
        assert 0.0 <= value <= 1.0


def test_ranked_frontier_human_pin_tie_break(app, reviewer_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    app.metrics.recompute([main_id])
    app.metrics.set_human_pin(main_id, 1.0)
    ranked = app.metrics.ranked_frontier(limit=5)
    assert ranked
    assert ranked[0]["id"] == main_id


def test_dispatch_thinker_single_node(app, reviewer_ctx):
    admit_main(app.tx_service, reviewer_ctx)
    result = app.scheduler.dispatch_thinker()
    assert result["status"] in {"completed", "failed"}
    assert "decision" in result or "reason" in result


def test_dispatch_thinker_cross_links_two_nodes(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("accept_hypothesis_with_link.json")
    payload["subject_node_id"] = main_id
    payload["proposed_links"][0]["to_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    outcome = app.reviewer.review_report(reviewer_ctx, report.id)
    assert outcome.decision == "ACCEPT"

    result = app.scheduler.dispatch_thinker()
    assert result["status"] == "completed"
    assert result["decision"] in {"ACCEPT", "REJECT", "PARTIAL_ACCEPT"}


def test_mark_stuck_on_budget_exhaustion(app, reviewer_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    app.repo.override_budget(main_id, "attempt", 0)
    app.repo.conn.commit()
    result = app.scheduler.dispatch_next(node_id=main_id)
    assert result["status"] == "blocked"
    obj = app.repo.get_object(main_id)
    assert obj.status == "STUCK"
    frontier_ids = {o.id for o in app.repo.get_frontier(limit=100)}
    assert main_id not in frontier_ids


def test_human_resolve_reject(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("needs_human.json")
    payload["subject_node_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    outcome = app.reviewer.review_report(reviewer_ctx, report.id)
    assert outcome.decision == "NEEDS_HUMAN"

    human_ctx = RoleContext(role=AgentRole.HUMAN, run_id="run_human")
    resolved = app.reviewer.human_resolve(
        human_ctx, report.id, decision="REJECT", note="not enough evidence"
    )
    assert resolved.decision == "REJECT"


def test_human_resolve_accept(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("accept_hypothesis_with_link.json")
    payload = copy.deepcopy(payload)
    payload["subject_node_id"] = main_id
    payload["proposed_links"][0]["to_id"] = main_id
    payload["needs_human"] = True
    report = app.report_intake.submit(worker_ctx, payload)
    outcome = app.reviewer.review_report(reviewer_ctx, report.id)
    assert outcome.decision == "NEEDS_HUMAN"

    human_ctx = RoleContext(role=AgentRole.HUMAN, run_id="run_human")
    resolved = app.reviewer.human_resolve(human_ctx, report.id, decision="ACCEPT")
    assert resolved.decision == "ACCEPT"
    stats = app.tx_service.graph_statistics()
    assert stats["object_count"] == 2


def test_human_resolve_rejects_non_human_role(app, reviewer_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("needs_human.json")
    payload["subject_node_id"] = main_id
    report = app.report_intake.submit(reviewer_ctx, payload)
    app.reviewer.review_report(reviewer_ctx, report.id)
    try:
        app.reviewer.human_resolve(reviewer_ctx, report.id, decision="REJECT")
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass


def test_auto_supersede_strengthens_chain(app, reviewer_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)

    weaker = build_object(
        object_type="Hypothesis",
        title="Weaker variant",
        statement="Some even integers are the sum of two primes.",
        origin_kind="worker_report",
        origin_refs=[main_id],
        run_id=reviewer_ctx.run_id,
        information_gain="Weaker baseline claim.",
    )
    stronger = build_object(
        object_type="Hypothesis",
        title="Stronger variant",
        statement="All even integers below 10^9 are the sum of two primes.",
        origin_kind="worker_report",
        origin_refs=[main_id],
        run_id=reviewer_ctx.run_id,
        information_gain="Stronger, more specific claim.",
    )
    setup_tx = Transaction(
        id=new_tx_id(),
        actor_role=reviewer_ctx.role.value,
        actor_run_id=reviewer_ctx.run_id,
        summary="Set up strengthens chain",
        ops=[
            AppendNodeOp(object=weaker),
            AppendNodeOp(object=stronger),
            CreateLinkOp(from_id=stronger.id, to_id=weaker.id, edge_type="strengthens"),
        ],
    )
    setup_result = app.tx_service.apply(reviewer_ctx, setup_tx)
    assert setup_result.accepted, setup_result.rejections

    counterexample = build_object(
        object_type="Counterexample",
        title="Disproof of weaker variant",
        statement="Explicit even integer with no two-prime sum.",
        origin_kind="worker_report",
        origin_refs=[main_id],
        run_id=reviewer_ctx.run_id,
        information_gain="Disproves the weaker hypothesis.",
    )
    disprove_tx = Transaction(
        id=new_tx_id(),
        actor_role=reviewer_ctx.role.value,
        actor_run_id=reviewer_ctx.run_id,
        summary="Disprove weaker variant",
        ops=[
            AppendNodeOp(object=counterexample),
            CreateLinkOp(from_id=weaker.id, to_id=counterexample.id, edge_type="disproved_by"),
            SetStatusOp(
                node_id=weaker.id,
                status="DISPROVED",
                evidence_refs=[counterexample.id],
                reason="Reviewer accepted counterexample",
            ),
        ],
    )
    disprove_result = app.tx_service.apply(reviewer_ctx, disprove_tx)
    assert disprove_result.accepted, disprove_result.rejections

    app.reviewer._auto_supersede(disprove_tx.ops, reviewer_ctx)

    refreshed_stronger = app.repo.get_object(stronger.id)
    assert refreshed_stronger.status == "SUPERSEDED"


# ---------------------------------------------------------------------------
# MCP tool layer (P3.1 human ops, P3.2 thinker dispatch, P4.1 search/read,
# P4.4 duplicates, P6 formal export scaffold). These call the actual
# @mcp.tool()-decorated functions directly (FastMCP leaves them as plain
# callables), against an isolated tmp-path app rather than the real project
# repo, via the `mcp_app` fixture below.
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_app(app, runtime):
    mcp_server._app = app
    mcp_server._acl = ACL(runtime.roles_config)
    yield app
    mcp_server._app = None
    mcp_server._acl = None


def test_pin_node_tool(mcp_app, reviewer_ctx):
    main_id = admit_main(mcp_app.tx_service, reviewer_ctx)
    result = mcp_server.pin_node(role="human", run_id="run_pin", node_id=main_id, weight=0.7)
    assert result.node_id == main_id
    assert result.weight == 0.7


def test_freeze_and_unfreeze_node_tool(mcp_app, reviewer_ctx):
    main_id = admit_main(mcp_app.tx_service, reviewer_ctx)
    frozen = mcp_server.freeze_node(
        role="human", run_id="run_freeze", node_id=main_id, reason="pause"
    )
    assert frozen.status == "FROZEN"
    assert mcp_app.repo.get_object(main_id).status == "FROZEN"

    unfrozen = mcp_server.unfreeze_node(role="human", run_id="run_unfreeze", node_id=main_id)
    assert unfrozen.status == "ACTIVE"
    assert mcp_app.repo.get_object(main_id).status == "ACTIVE"


def test_inject_literature_tool(mcp_app):
    result = mcp_server.inject_literature(
        role="human",
        run_id="run_lit",
        title="Vinogradov's theorem",
        statement="Every sufficiently large odd integer is the sum of three primes.",
        information_gain="Adjacent known result useful for cross-referencing.",
        object_type="Paper",
    )
    obj = mcp_app.repo.get_object(result.node_id)
    assert obj is not None
    assert obj.type == "Paper"
    assert obj.title == "Vinogradov's theorem"


def test_override_budget_tool(mcp_app, reviewer_ctx):
    main_id = admit_main(mcp_app.tx_service, reviewer_ctx)
    result = mcp_server.override_budget(
        role="human", run_id="run_budget", node_id=main_id, budget_name="attempt", new_limit=42
    )
    assert result.new_limit == 42
    budget = mcp_app.repo.get_budget(main_id)
    assert budget["attempt_budget"] == 42


def test_resolve_needs_human_tool(mcp_app, reviewer_ctx, worker_ctx):
    main_id = admit_main(mcp_app.tx_service, reviewer_ctx)
    payload = load_report_fixture("needs_human.json")
    payload["subject_node_id"] = main_id
    report = mcp_app.report_intake.submit(worker_ctx, payload)
    mcp_app.reviewer.review_report(reviewer_ctx, report.id)

    result = mcp_server.resolve_needs_human(
        role="human",
        run_id="run_human_tool",
        report_id=report.id,
        decision="REJECT",
        note="insufficient",
    )
    assert result.decision == "REJECT"


def test_dispatch_thinker_tool(mcp_app, reviewer_ctx):
    admit_main(mcp_app.tx_service, reviewer_ctx)
    result = mcp_server.dispatch_thinker(role="scheduler", run_id="run_thinker_tool")
    assert result.status in {"completed", "failed"}


def test_search_and_read_tools(mcp_app, reviewer_ctx):
    main_id = admit_main(mcp_app.tx_service, reviewer_ctx)
    technique = build_object(
        object_type="Technique",
        title="Sieve method",
        statement="A sieve-based technique for bounding prime gaps.",
        origin_kind="human_directive",
        origin_refs=["bootstrap"],
        run_id=reviewer_ctx.run_id,
        information_gain="Reusable technique.",
    )
    tx = Transaction(
        id=new_tx_id(),
        actor_role=reviewer_ctx.role.value,
        actor_run_id=reviewer_ctx.run_id,
        summary="Add technique",
        ops=[AppendNodeOp(object=technique)],
    )
    assert mcp_app.tx_service.apply(reviewer_ctx, tx).accepted

    hits = mcp_server.semantic_search(
        role="human", run_id="run_search", query="prime sums", limit=5
    )
    assert any(h["id"] == main_id for h in hits)

    similar = mcp_server.find_similar(role="human", run_id="run_similar", node_id=main_id, limit=5)
    assert all(h["id"] != main_id for h in similar)

    orphans = mcp_server.find_orphans(role="human", run_id="run_orphans", limit=50)
    orphan_ids = {o["id"] for o in orphans}
    assert main_id in orphan_ids
    assert technique.id in orphan_ids

    dead = mcp_server.find_dead_nodes(role="human", run_id="run_dead", limit=50)
    assert dead == []

    events = mcp_server.timeline(role="human", run_id="run_timeline", limit=200)
    assert isinstance(events, list)
    assert len(events) > 0

    nearest = mcp_server.nearest_main(role="human", run_id="run_nearest", node_id=main_id)
    assert nearest.node_id == main_id
    assert nearest.distance == 0

    techniques = mcp_server.search_techniques(
        role="human", run_id="run_tech", query="sieve", limit=5
    )
    assert any(t["id"] == technique.id for t in techniques)

    no_defs = mcp_server.search_by_definition(role="human", run_id="run_def", limit=5)
    assert no_defs == []


def test_find_duplicate_and_merge_duplicate_tools(mcp_app, reviewer_ctx):
    main_id = admit_main(mcp_app.tx_service, reviewer_ctx)
    duplicate = build_object(
        object_type="Hypothesis",
        title="Near duplicate",
        statement="Every even integer greater than 2 is the sum of two primes.",
        origin_kind="worker_report",
        origin_refs=[main_id],
        run_id=reviewer_ctx.run_id,
        information_gain="Should be flagged as near-duplicate.",
    )
    tx = Transaction(
        id=new_tx_id(),
        actor_role=reviewer_ctx.role.value,
        actor_run_id=reviewer_ctx.run_id,
        summary="Add near duplicate",
        ops=[AppendNodeOp(object=duplicate)],
    )
    assert mcp_app.tx_service.apply(reviewer_ctx, tx).accepted

    hits = mcp_server.find_duplicate(
        role="human",
        run_id="run_dup",
        statement="Every even integer greater than 2 is the sum of two primes.",
        limit=5,
    )
    assert any(h.node_id == main_id for h in hits)

    merge_result = mcp_server.merge_duplicate(
        role="human", run_id="run_merge", representative_id=main_id, member_id=duplicate.id
    )
    assert merge_result.accepted, merge_result.rejections


def test_export_formal_tool(mcp_app, reviewer_ctx):
    main_id = admit_main(mcp_app.tx_service, reviewer_ctx)
    result = mcp_server.export_formal(role="human", run_id="run_export", node_id=main_id)
    assert result.node_id == main_id
    assert "NOT VERIFIED" in result.content


def test_cli_pin_dispatch_activity(mcp_app, reviewer_ctx, capsys):
    main_id = admit_main(mcp_app.tx_service, reviewer_ctx)
    assert cli_main.main(["pin", main_id, "--weight", "0.5"]) == 0
    assert main_id in capsys.readouterr().out

    assert cli_main.main(["dispatch", "thinker"]) == 0
    capsys.readouterr()

    assert cli_main.main(["activity"]) == 0
    assert "Agent activity" in capsys.readouterr().out


def test_cli_resolve_report(mcp_app, reviewer_ctx, worker_ctx):
    main_id = admit_main(mcp_app.tx_service, reviewer_ctx)
    payload = load_report_fixture("needs_human.json")
    payload["subject_node_id"] = main_id
    report = mcp_app.report_intake.submit(worker_ctx, payload)
    mcp_app.reviewer.review_report(reviewer_ctx, report.id)

    exit_code = cli_main.main(["resolve-report", report.id, "--reject", "--note", "no"])
    assert exit_code == 0


# ---------------------------------------------------------------------------
# P5.2 vault v2, P5.4 activity v2, P7 daemon/backup/analytics
# ---------------------------------------------------------------------------


def test_vault_statistics_and_timeline_regenerate_on_apply(app, reviewer_ctx):
    admit_main(app.tx_service, reviewer_ctx)
    stats_path = app.config.vault_dir / "00_meta" / "STATISTICS.md"
    timeline_path = app.config.vault_dir / "00_meta" / "TIMELINE.md"
    assert stats_path.exists()
    assert timeline_path.exists()
    assert "Total objects: 1" in stats_path.read_text(encoding="utf-8")
    assert "Research timeline" in timeline_path.read_text(encoding="utf-8")


def test_activity_dashboard_needs_human_section(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("needs_human.json")
    payload["subject_node_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    app.reviewer.review_report(reviewer_ctx, report.id)

    path = app.activity.project_dashboard(force=True)
    content = path.read_text(encoding="utf-8")
    assert "## Needs human" in content
    assert report.id in content


def test_scheduler_daemon_run_once(app, reviewer_ctx):
    admit_main(app.tx_service, reviewer_ctx)
    daemon = SchedulerDaemon(app, thinker_cadence=1)
    summary = daemon.run_once()
    assert summary["poll"] == 1
    assert summary["worker_results"]
    assert summary["thinker_result"] is not None


def test_scheduler_daemon_run_forever_bounded(app, reviewer_ctx):
    admit_main(app.tx_service, reviewer_ctx)
    daemon = SchedulerDaemon(app, poll_interval_seconds=0, thinker_cadence=5)
    iterations = daemon.run_forever(max_iterations=2)
    assert iterations == 2


def test_backup_and_restore_roundtrip(app, runtime, reviewer_ctx, tmp_path):
    admit_main(app.tx_service, reviewer_ctx)
    service = BackupService(app.repo, runtime)
    snapshot_dir = service.backup(tmp_path / "backups")
    assert (snapshot_dir / "research.db").exists()
    assert (snapshot_dir / "manifest.json").exists()

    restore_config = dataclasses.replace(runtime, db_path=tmp_path / "restored" / "research.db")
    restore_service = BackupService(app.repo, restore_config)
    restored_path = restore_service.restore(snapshot_dir)
    assert restored_path == restore_config.db_path

    from research_os.store.connection import connect
    from research_os.store.repository import Repository

    restored_conn = connect(restore_config.db_path)
    try:
        restored_repo = Repository(restored_conn)
        assert len(restored_repo.list_objects(limit=100)) == len(app.repo.list_objects(limit=100))
    finally:
        restored_conn.close()


def test_backup_restore_refuses_overwrite_without_force(app, runtime, reviewer_ctx, tmp_path):
    admit_main(app.tx_service, reviewer_ctx)
    service = BackupService(app.repo, runtime)
    snapshot_dir = service.backup(tmp_path / "backups")
    try:
        service.restore(snapshot_dir)
        raise AssertionError("expected FileExistsError")
    except FileExistsError:
        pass


def test_backup_export_jsonl(app, runtime, reviewer_ctx, tmp_path):
    admit_main(app.tx_service, reviewer_ctx)
    service = BackupService(app.repo, runtime)
    path = service.export_jsonl(tmp_path / "export.jsonl")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert any('"record_type": "object"' in line for line in lines)


def test_weekly_analytics_generate(app, runtime, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("accept_hypothesis_with_link.json")
    payload["subject_node_id"] = main_id
    payload["proposed_links"][0]["to_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    app.reviewer.review_report(reviewer_ctx, report.id)

    analytics = WeeklyAnalytics(app.repo, runtime.vault_dir)
    path = analytics.generate(days=7)
    content = path.read_text(encoding="utf-8")
    assert "Weekly research health" in content
    assert "ACCEPT" in content

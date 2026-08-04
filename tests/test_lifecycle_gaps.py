"""Report intake conflict and lifecycle tests."""

from __future__ import annotations

import json
import sqlite3

import pytest
from conftest import admit_main, load_report_fixture

from research_os.kernel.types import InvariantCode, KernelError
from research_os.reports.types import ReportStatus
from research_os.store.migrations import SCHEMA_VERSION, migrate


def test_submit_conflict_for_same_run(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("accept_hypothesis_with_link.json")
    payload["subject_node_id"] = main_id
    payload["proposed_links"][0]["to_id"] = main_id
    app.report_intake.submit(worker_ctx, payload)
    conflict = dict(payload)
    conflict["information_delta"] = ["A different information delta"]
    with pytest.raises(ValueError, match="different content"):
        app.report_intake.submit(worker_ctx, conflict)


def test_submit_idempotent_same_content(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("accept_hypothesis_with_link.json")
    payload["subject_node_id"] = main_id
    payload["proposed_links"][0]["to_id"] = main_id
    first = app.report_intake.submit(worker_ctx, payload)
    second = app.report_intake.submit(worker_ctx, payload)
    assert first.id == second.id


def test_needs_human_status(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("needs_human.json")
    payload["subject_node_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    outcome = app.reviewer.review_report(reviewer_ctx, report.id)
    assert outcome.decision == "NEEDS_HUMAN"
    refreshed = app.repo.get_report(report.id)
    assert refreshed is not None
    assert refreshed.status == ReportStatus.NEEDS_HUMAN.value


def test_v5_db_backfills_entities(tmp_path):
    db_path = tmp_path / "v5.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version(version) VALUES (5)")
    conn.executescript(
        """
        CREATE TABLE reports (
            id TEXT PRIMARY KEY,
            report_type TEXT NOT NULL,
            subject_node_id TEXT NOT NULL,
            status TEXT NOT NULL,
            run_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            content_fingerprint TEXT
        );
        CREATE TABLE report_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            claim_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            speculative INTEGER NOT NULL DEFAULT 0,
            evidence_refs_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );
        CREATE TABLE citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            ref TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE candidate_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            op_index INTEGER NOT NULL,
            op_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE agent_runs (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            node_scope TEXT,
            task_label TEXT,
            model_profile TEXT,
            reasoning_effort TEXT,
            resolved_model_id TEXT,
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            ended_at TEXT,
            last_result_summary TEXT,
            error_code TEXT,
            error_message TEXT
        );
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            status TEXT NOT NULL,
            priority REAL NOT NULL DEFAULT 0,
            assigned_run_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    payload = {
        "report_type": "worker",
        "subject_node_id": "ros_mc_test",
        "information_delta": ["delta"],
        "claims": [{"id": "c1", "text": "claim"}],
        "proposed_objects": [],
        "proposed_links": [],
        "literature_refs": [],
    }
    conn.execute(
        """
        INSERT INTO reports(
            id, report_type, subject_node_id, status, run_id,
            payload_json, created_at, content_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            "ros_report_test",
            "worker",
            "ros_mc_test",
            "PENDING",
            "run_worker_test",
            json.dumps(payload),
            "2026-01-01T00:00:00",
        ),
    )
    conn.commit()
    migrate(conn)
    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    fingerprint = conn.execute(
        "SELECT content_fingerprint FROM reports WHERE id = 'ros_report_test'"
    ).fetchone()[0]
    assert fingerprint
    claim_count = conn.execute(
        "SELECT COUNT(*) FROM report_claims WHERE report_id = 'ros_report_test'"
    ).fetchone()[0]
    assert claim_count == 1


def test_budget_exhaustion_raises(app, reviewer_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    app.repo.consume_node_budget(main_id, "attempt", 8.0)
    app.repo.conn.commit()
    with pytest.raises(KernelError) as exc:
        app.budgets.consume(
            run_id="run_budget",
            node_id=main_id,
            budget_name="attempt",
            amount=1.0,
        )
    assert exc.value.code == InvariantCode.BUDGET_EXHAUSTED


def test_sandbox_hook_whitelist():
    from research_os.agents.worker.sandbox import (
        WORKER_MCP_TOOLS,
        cleanup_worker_sandbox,
        create_worker_sandbox,
    )

    sandbox = create_worker_sandbox()
    try:
        hook = (sandbox / ".cursor" / "hooks" / "allow_research_mcp.py").read_text(encoding="utf-8")
        assert "submit_report" in hook
        assert "review_report" not in WORKER_MCP_TOOLS
    finally:
        cleanup_worker_sandbox(sandbox)

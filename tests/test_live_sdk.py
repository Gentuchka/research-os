"""Opt-in live Cursor SDK smoke test."""

from __future__ import annotations

import os

import pytest
from conftest import admit_main

from research_os.kernel.types import AgentRole, RoleContext

pytestmark = pytest.mark.skipif(
    os.environ.get("CURSOR_API_KEY") is None
    or os.environ.get("RESEARCH_OS_LIVE_SDK_TEST") != "1",
    reason="Set CURSOR_API_KEY and RESEARCH_OS_LIVE_SDK_TEST=1 to run live SDK smoke test",
)


def test_live_cursor_sdk_worker_smoke(app, reviewer_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    os.environ["RESEARCH_OS_USE_LIVE_SDK"] = "1"
    run_id = "run_live_smoke"
    app.repo.start_run(run_id, "worker", node_scope=main_id, task_label="Live smoke")
    app.repo.conn.commit()
    worker_ctx = RoleContext(role=AgentRole.WORKER, run_id=run_id, node_scope=main_id)
    report = app.scheduler.worker_runtime.cursor_worker.investigate(worker_ctx, main_id)
    assert report.subject_node_id == main_id

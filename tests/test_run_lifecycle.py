"""P2 lifecycle and budget tests."""

from __future__ import annotations

from conftest import admit_main


def test_budget_usage_recorded(app, reviewer_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    result = app.scheduler.dispatch_next(node_id=main_id)
    assert result["status"] == "completed"
    usage = app.repo.list_budget_usage(result["worker_run_id"])
    assert any(row["budget_name"] == "dispatch" for row in usage)


def test_stale_run_detection(app, reviewer_ctx):
    app.repo.start_run("run_stale", "worker", node_scope="ros_mc_x", task_label="stale")
    app.repo.conn.commit()
    stale = app.repo.list_stale_runs(0)
    assert any(row["id"] == "run_stale" for row in stale)


def test_cancel_run(app, reviewer_ctx):
    app.repo.start_run("run_cancel", "worker", node_scope="ros_mc_x", task_label="cancel me")
    app.repo.conn.commit()
    result = app.scheduler.cancel_run("run_cancel")
    assert result["status"] == "cancelled"

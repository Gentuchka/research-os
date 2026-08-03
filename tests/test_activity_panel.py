"""Activity panel projection tests."""

from __future__ import annotations

from conftest import admit_main


def test_activity_panel_readable(app, reviewer_ctx):
    admit_main(app.tx_service, reviewer_ctx)
    app.repo.start_run("run_panel", "worker", node_scope="ros_mc_test", task_label="Testing panel")
    app.repo.conn.commit()
    path = app.activity.project_dashboard(force=True)
    text = path.read_text(encoding="utf-8")
    assert "Working now" in text
    assert "worker" in text.lower()
    assert "{" not in text[:200]

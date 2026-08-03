"""Scheduler and worker dispatch tests."""

from __future__ import annotations

from conftest import admit_main


def test_scheduler_dispatch(app, reviewer_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    result = app.scheduler.dispatch_next(node_id=main_id)
    assert result["status"] == "completed"
    assert result["decision"] in {"ACCEPT", "REJECT", "PARTIAL_ACCEPT"}
    activity = (app.config.vault_dir / "00_meta" / "AGENT_ACTIVITY.md").read_text(encoding="utf-8")
    assert "Recently finished" in activity

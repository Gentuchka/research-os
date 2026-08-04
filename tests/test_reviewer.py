"""P1 report and reviewer tests."""

from __future__ import annotations

from conftest import admit_main, load_report_fixture


def test_submit_and_review_accept(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("accept_hypothesis_with_link.json")
    payload["subject_node_id"] = main_id
    payload["proposed_links"][0]["to_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    outcome = app.reviewer.review_report(reviewer_ctx, report.id)
    assert outcome.decision == "ACCEPT"
    stats = app.tx_service.graph_statistics()
    assert stats["object_count"] == 2
    report_note = app.config.vault_dir / "03_reports" / f"{report.id}.md"
    assert report_note.exists()


def test_reject_low_information(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("reject_low_information.json")
    payload["subject_node_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    outcome = app.reviewer.review_report(reviewer_ctx, report.id)
    assert outcome.decision == "REJECT"
    assert "SLOP_LOW_INFORMATION" in outcome.reason_codes


def test_review_is_idempotent(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("accept_hypothesis_with_link.json")
    payload["subject_node_id"] = main_id
    payload["proposed_links"][0]["to_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    first = app.reviewer.review_report(reviewer_ctx, report.id)
    second = app.reviewer.review_report(reviewer_ctx, report.id)
    assert first.decision == second.decision
    assert app.repo.has_review_decision(report.id)

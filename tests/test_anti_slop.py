"""Additional anti-slop and adjudication tests."""

from __future__ import annotations

from conftest import admit_main, load_report_fixture


def test_reject_unsupported_claim(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("unsupported_claim.json")
    payload["subject_node_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    outcome = app.reviewer.review_report(reviewer_ctx, report.id)
    assert outcome.decision == "REJECT"
    assert "SLOP_UNSUPPORTED_CLAIM" in outcome.reason_codes


def test_needs_human(app, reviewer_ctx, worker_ctx):
    main_id = admit_main(app.tx_service, reviewer_ctx)
    payload = load_report_fixture("needs_human.json")
    payload["subject_node_id"] = main_id
    report = app.report_intake.submit(worker_ctx, payload)
    outcome = app.reviewer.review_report(reviewer_ctx, report.id)
    assert outcome.decision == "NEEDS_HUMAN"

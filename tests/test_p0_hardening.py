"""P0 hardening tests."""

from __future__ import annotations

from conftest import admit_main

from research_os.kernel.types import (
    CreateLinkOp,
    InvariantCode,
    SetStatusOp,
    Transaction,
    new_tx_id,
)


def test_rejects_empty_transaction(service, reviewer_ctx):
    admit_main(service, reviewer_ctx)
    result = service.apply(
        reviewer_ctx,
        Transaction(
            id=new_tx_id(),
            actor_role="reviewer",
            actor_run_id=reviewer_ctx.run_id,
            summary="noop extra",
            ops=[],
        ),
    )
    assert not result.accepted
    assert result.rejections[0]["code"] == "INVALID_OPERATION"


def test_rejects_self_link(service, reviewer_ctx):
    main_id = admit_main(service, reviewer_ctx)
    tx = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id=reviewer_ctx.run_id,
        summary="self link",
        ops=[CreateLinkOp(from_id=main_id, to_id=main_id, edge_type="depends_on")],
    )
    result = service.apply(reviewer_ctx, tx)
    assert not result.accepted
    assert result.rejections[0]["code"] == InvariantCode.INV_CYCLE.value


def test_status_requires_existing_evidence(service, reviewer_ctx):
    main_id = admit_main(service, reviewer_ctx)
    tx = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id=reviewer_ctx.run_id,
        summary="bad evidence",
        ops=[
            SetStatusOp(
                node_id=main_id,
                status="PROVED",
                evidence_refs=["ros_missing_01"],
                reason="bad",
            )
        ],
    )
    result = service.apply(reviewer_ctx, tx)
    assert not result.accepted
    assert result.rejections[0]["code"] == InvariantCode.NOT_FOUND.value

"""Invariant engine tests."""

from __future__ import annotations

import pytest
from conftest import admit_main

from research_os.kernel.builders import build_object
from research_os.kernel.invariants import InvariantEngine
from research_os.kernel.types import (
    AppendNodeOp,
    CreateLinkOp,
    InvariantCode,
    KernelError,
    SetStatusOp,
    Transaction,
    new_tx_id,
)


def test_rejects_missing_provenance(runtime, service, reviewer_ctx):
    repo = service.repo
    engine = InvariantEngine(repo)
    obj = build_object(
        object_type="Hypothesis",
        title="Bad",
        statement="No provenance refs.",
        origin_kind="worker_report",
        origin_refs=[],
        run_id="run_x",
        information_gain="Should fail.",
    )
    tx = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id="run_x",
        summary="bad",
        ops=[AppendNodeOp(object=obj)],
    )
    with pytest.raises(KernelError) as exc:
        engine.validate(tx)
    assert exc.value.code == InvariantCode.INV_NO_PROVENANCE


def test_rejects_duplicate_content(runtime, service, reviewer_ctx):
    main_id = admit_main(service, reviewer_ctx)
    main = service.get_node(main_id)
    assert main is not None
    obj = build_object(
        object_type=main["type"],
        title=main["title"],
        statement=main["statement"],
        origin_kind="existing_hypothesis",
        origin_refs=[main_id],
        run_id=reviewer_ctx.run_id,
        information_gain="Duplicate of main conjecture statement.",
    )
    tx = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id=reviewer_ctx.run_id,
        summary="dup",
        ops=[AppendNodeOp(object=obj)],
    )
    result = service.apply(reviewer_ctx, tx)
    assert not result.accepted
    assert result.rejections[0]["code"] == InvariantCode.DUPLICATE_CONTENT.value


def test_rejects_cycle(runtime, service, reviewer_ctx):
    a = build_object(
        object_type="Hypothesis",
        title="A",
        statement="A implies B.",
        origin_kind="human_directive",
        origin_refs=["bootstrap"],
        run_id=reviewer_ctx.run_id,
        information_gain="Node A.",
    )
    b = build_object(
        object_type="Hypothesis",
        title="B",
        statement="B implies A.",
        origin_kind="human_directive",
        origin_refs=["bootstrap"],
        run_id=reviewer_ctx.run_id,
        information_gain="Node B.",
    )
    tx1 = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id=reviewer_ctx.run_id,
        summary="admit a and b",
        ops=[AppendNodeOp(object=a), AppendNodeOp(object=b)],
    )
    assert service.apply(reviewer_ctx, tx1).accepted
    tx2 = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id=reviewer_ctx.run_id,
        summary="cycle",
        ops=[
            CreateLinkOp(from_id=a.id, to_id=b.id, edge_type="depends_on"),
            CreateLinkOp(from_id=b.id, to_id=a.id, edge_type="depends_on"),
        ],
    )
    result = service.apply(reviewer_ctx, tx2)
    assert not result.accepted
    assert result.rejections[0]["code"] == InvariantCode.INV_CYCLE.value


def test_status_requires_evidence(runtime, service, reviewer_ctx):
    main_id = admit_main(service, reviewer_ctx)
    tx = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id=reviewer_ctx.run_id,
        summary="prove without evidence",
        ops=[
            SetStatusOp(
                node_id=main_id,
                status="PROVED",
                evidence_refs=[],
                reason="unsupported",
            )
        ],
    )
    result = service.apply(reviewer_ctx, tx)
    assert not result.accepted
    assert result.rejections[0]["code"] == InvariantCode.INV_UNSUPPORTED_CLAIM.value

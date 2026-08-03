"""End-to-end P0 flow."""

from __future__ import annotations

import pytest
from conftest import admit_main

from research_os.kernel.builders import build_object
from research_os.kernel.types import (
    AppendMetricOp,
    AppendNodeOp,
    CreateLinkOp,
    InvariantCode,
    KernelError,
    MergeEquivalenceClassOp,
    Transaction,
    new_tx_id,
)


def test_e2e_main_hypothesis_link_metric(service, reviewer_ctx):
    main_id = admit_main(service, reviewer_ctx)
    hyp = build_object(
        object_type="Hypothesis",
        title="Even n > 4",
        statement="Every even integer greater than 4 is a sum of two primes.",
        origin_kind="existing_hypothesis",
        origin_refs=[main_id],
        run_id=reviewer_ctx.run_id,
        information_gain="Specializes main conjecture to n > 4.",
    )
    tx = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id=reviewer_ctx.run_id,
        summary="Admit hypothesis and link",
        ops=[
            AppendNodeOp(object=hyp),
            CreateLinkOp(
                from_id=hyp.id,
                to_id=main_id,
                edge_type="specializes",
            ),
            AppendMetricOp(
                node_id=hyp.id,
                metric_name="importance",
                value=0.8,
                method="manual",
                version="v1",
            ),
        ],
    )
    result = service.apply(reviewer_ctx, tx)
    assert result.accepted, result.rejections
    assert hyp.id in result.affected_node_ids
    stats = service.graph_statistics()
    assert stats["object_count"] == 2
    assert stats["math_edge_count"] == 1
    history = service.history(hyp.id)
    assert any(event["event_type"] == "NODE_ADMITTED" for event in history)


def test_equivalence_merge(service, reviewer_ctx):
    main_id = admit_main(service, reviewer_ctx)
    a = build_object(
        object_type="Hypothesis",
        title="Variant A",
        statement="Statement variant A for merge test.",
        origin_kind="existing_hypothesis",
        origin_refs=[main_id],
        run_id=reviewer_ctx.run_id,
        information_gain="First variant.",
    )
    b = build_object(
        object_type="Hypothesis",
        title="Variant B",
        statement="Statement variant B for merge test.",
        origin_kind="existing_hypothesis",
        origin_refs=[main_id],
        run_id=reviewer_ctx.run_id,
        information_gain="Duplicate variant.",
    )
    tx1 = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id=reviewer_ctx.run_id,
        summary="admit variants",
        ops=[AppendNodeOp(object=a), AppendNodeOp(object=b)],
    )
    assert service.apply(reviewer_ctx, tx1).accepted
    tx2 = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id=reviewer_ctx.run_id,
        summary="merge equivalence",
        ops=[
            MergeEquivalenceClassOp(
                representative_id=a.id,
                member_id=b.id,
            )
        ],
    )
    result = service.apply(reviewer_ctx, tx2)
    assert result.accepted, result.rejections
    member = service.get_node(b.id)
    assert member is not None
    assert member["status"] == "SUPERSEDED"
    assert member["is_class_representative"] is False


def test_worker_cannot_apply(worker_ctx, service, reviewer_ctx):
    main_id = admit_main(service, reviewer_ctx)
    hyp = build_object(
        object_type="Hypothesis",
        title="Worker attempt",
        statement="Worker should not write this.",
        origin_kind="existing_hypothesis",
        origin_refs=[main_id],
        run_id=worker_ctx.run_id,
        information_gain="Should be rejected by ACL.",
    )
    tx = Transaction(
        id=new_tx_id(),
        actor_role="worker",
        actor_run_id=worker_ctx.run_id,
        summary="worker tries write",
        ops=[AppendNodeOp(object=hyp)],
    )
    with pytest.raises(KernelError) as exc:
        service.apply(worker_ctx, tx)
    assert exc.value.code == InvariantCode.ACL_DENIED

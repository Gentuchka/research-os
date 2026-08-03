"""Vault projection tests."""

from __future__ import annotations

from conftest import admit_main

from research_os.kernel.builders import build_object
from research_os.kernel.types import AppendNodeOp, Transaction, new_tx_id


def test_projection_writes_object_note(runtime, service, reviewer_ctx):
    main_id = admit_main(service, reviewer_ctx)
    hyp = build_object(
        object_type="Hypothesis",
        title="Weak Goldbach",
        statement="Every large even integer is a sum of two primes.",
        origin_kind="existing_hypothesis",
        origin_refs=[main_id],
        run_id=reviewer_ctx.run_id,
        information_gain="Weaker variant for testing.",
    )
    tx = Transaction(
        id=new_tx_id(),
        actor_role="reviewer",
        actor_run_id=reviewer_ctx.run_id,
        summary="admit hypothesis",
        ops=[AppendNodeOp(object=hyp)],
    )
    assert service.apply(reviewer_ctx, tx).accepted
    path = runtime.vault_dir / "02_objects" / "Hypothesis" / f"{hyp.id}.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Weak Goldbach" in text
    assert hyp.id in text
    frontier = (runtime.vault_dir / "04_frontier" / "current.md").read_text(encoding="utf-8")
    assert hyp.title in frontier

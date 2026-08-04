"""MCP server ACL and role-binding tests."""

from __future__ import annotations

import pytest
from ulid import ULID

from research_os.kernel.types import InvariantCode, KernelError
from research_os.mcp_server.server import _bootstrap, _ctx, _guard


def test_role_mismatch_rejected():
    app = _bootstrap()
    run_id = f"run_bound_worker_{ULID()}"
    app.repo.start_run(run_id, "worker", node_scope="ros_mc_x", task_label="t")
    app.repo.conn.commit()
    with pytest.raises(KernelError) as exc:
        _ctx("reviewer", run_id)
    assert exc.value.code == InvariantCode.ACL_DENIED


def test_worker_cannot_review_report():
    app = _bootstrap()
    run_id = f"run_worker_acl_{ULID()}"
    app.repo.start_run(run_id, "worker", node_scope="ros_mc_x", task_label="t")
    app.repo.conn.commit()
    ctx = _ctx("worker", run_id)
    with pytest.raises(KernelError) as exc:
        _guard(ctx, "review_report")
    assert exc.value.code == InvariantCode.ACL_DENIED


def test_scheduler_can_cancel_run():
    ctx = _ctx("scheduler", f"run_scheduler_op_{ULID()}")
    _guard(ctx, "cancel_run")


def test_reviewer_can_replay_projection():
    app = _bootstrap()
    run_id = f"run_reviewer_acl_{ULID()}"
    app.repo.start_run(run_id, "reviewer", node_scope="ros_mc_x", task_label="t")
    app.repo.conn.commit()
    ctx = _ctx("reviewer", run_id)
    _guard(ctx, "replay_projection")

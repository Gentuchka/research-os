"""ACL tests."""

from __future__ import annotations

import pytest

from research_os.acl import ACL
from research_os.config import RuntimeConfig
from research_os.kernel.types import AgentRole, InvariantCode, KernelError, RoleContext


def test_worker_denied_apply_transaction(runtime: RuntimeConfig):
    acl = ACL(runtime.roles_config)
    ctx = RoleContext(role=AgentRole.WORKER, run_id="run1")
    with pytest.raises(KernelError) as exc:
        acl.assert_tool(ctx, "apply_transaction")
    assert exc.value.code == InvariantCode.ACL_DENIED


def test_reviewer_allowed_apply_transaction(runtime: RuntimeConfig):
    acl = ACL(runtime.roles_config)
    ctx = RoleContext(role=AgentRole.REVIEWER, run_id="run1")
    acl.assert_tool(ctx, "apply_transaction")

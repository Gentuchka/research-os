"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from research_os.config import RuntimeConfig
from research_os.factory import build_service
from research_os.kernel.builders import build_object
from research_os.kernel.transaction_service import TransactionService
from research_os.kernel.types import (
    AgentRole,
    AppendNodeOp,
    RoleContext,
    Transaction,
    new_tx_id,
)


@pytest.fixture
def runtime(tmp_path: Path) -> RuntimeConfig:
    repo = tmp_path / "repo"
    shutil.copytree(Path(__file__).resolve().parents[1] / "configs", repo / "configs")
    shutil.copytree(Path(__file__).resolve().parents[1] / "schemas", repo / "schemas")
    shutil.copytree(Path(__file__).resolve().parents[1] / "vault", repo / "vault")
    (repo / "data" / "canonical").mkdir(parents=True)
    (repo / "data" / "transactions").mkdir(parents=True)
    return RuntimeConfig.load(repo, git_commit_enabled=False)


@pytest.fixture
def service(runtime: RuntimeConfig) -> TransactionService:
    return build_service(runtime)


@pytest.fixture
def reviewer_ctx() -> RoleContext:
    return RoleContext(role=AgentRole.REVIEWER, run_id="run_test")


@pytest.fixture
def worker_ctx() -> RoleContext:
    return RoleContext(role=AgentRole.WORKER, run_id="run_worker")


def admit_main(service: TransactionService, ctx: RoleContext) -> str:
    obj = build_object(
        object_type="MainConjecture",
        title="Goldbach",
        statement="Every even integer greater than 2 is the sum of two primes.",
        origin_kind="human_directive",
        origin_refs=["bootstrap"],
        run_id=ctx.run_id,
        information_gain="Establishes the main research target.",
    )
    tx = Transaction(
        id=new_tx_id(),
        actor_role=ctx.role.value,
        actor_run_id=ctx.run_id,
        summary="Admit main conjecture",
        ops=[AppendNodeOp(object=obj)],
    )
    result = service.apply(ctx, tx)
    assert result.accepted, result.rejections
    return obj.id

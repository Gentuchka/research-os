"""Shared pytest fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from research_os.config import RuntimeConfig
from research_os.factory import build_app
from research_os.kernel.builders import build_object
from research_os.kernel.types import AgentRole, AppendNodeOp, RoleContext, Transaction, new_tx_id


@pytest.fixture
def runtime(tmp_path: Path) -> RuntimeConfig:
    repo = tmp_path / "repo"
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "configs", repo / "configs")
    shutil.copytree(root / "schemas", repo / "schemas")
    shutil.copytree(root / "vault", repo / "vault")
    (repo / "data" / "canonical").mkdir(parents=True)
    (repo / "data" / "transactions").mkdir(parents=True)
    (repo / "data" / "rejections").mkdir(parents=True)
    return RuntimeConfig.load(repo, git_commit_enabled=False)


@pytest.fixture
def app(runtime: RuntimeConfig):
    return build_app(runtime)


@pytest.fixture
def service(app):
    return app.tx_service


@pytest.fixture
def reviewer_ctx() -> RoleContext:
    return RoleContext(role=AgentRole.REVIEWER, run_id="run_test")


@pytest.fixture
def worker_ctx() -> RoleContext:
    return RoleContext(role=AgentRole.WORKER, run_id="run_worker")


def admit_main(service, ctx: RoleContext) -> str:
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


def load_report_fixture(name: str) -> dict:
    path = Path(__file__).resolve().parent / "fixtures" / "reports" / name
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)

"""Atomic transaction application service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research_os.config import RuntimeConfig
from research_os.git_bridge.commit import commit_transaction
from research_os.kernel.invariants import InvariantEngine
from research_os.kernel.types import (
    AgentRole,
    InvariantCode,
    KernelError,
    RoleContext,
    Transaction,
)
from research_os.projection.vault import VaultProjector
from research_os.store.repository import Repository


@dataclass
class ApplyResult:
    tx_id: str
    accepted: bool
    rejections: list[dict[str, str]]
    affected_node_ids: list[str]
    git_commit_sha: str | None = None


class TransactionService:
    def __init__(
        self,
        repo: Repository,
        config: RuntimeConfig,
        projector: VaultProjector,
    ) -> None:
        self.repo = repo
        self.config = config
        self.projector = projector
        self.invariants = InvariantEngine(repo)

    def apply(self, ctx: RoleContext, tx: Transaction) -> ApplyResult:
        if ctx.role not in {AgentRole.REVIEWER, AgentRole.HUMAN}:
            raise KernelError(
                InvariantCode.ACL_DENIED,
                f"Role {ctx.role.value} cannot apply transactions",
            )
        try:
            self.invariants.validate(tx)
            affected = self.repo.apply_ops(tx.id, tx.ops)
            projected_paths = self.projector.project_nodes(affected)
            self.projector.project_frontier()
            git_sha = None
            if self.config.git_commit_enabled:
                git_sha = commit_transaction(
                    repo_root=self.config.repo_root,
                    tx=tx,
                    projected_paths=projected_paths,
                    transactions_dir=self.config.transactions_dir,
                )
            self.repo.record_transaction(
                tx_id=tx.id,
                actor_role=tx.actor_role,
                actor_run_id=tx.actor_run_id,
                summary=tx.summary,
                accepted=True,
                payload=tx.to_dict(),
                git_commit_sha=git_sha,
            )
            self.repo.conn.commit()
            return ApplyResult(
                tx_id=tx.id,
                accepted=True,
                rejections=[],
                affected_node_ids=affected,
                git_commit_sha=git_sha,
            )
        except KernelError as exc:
            self.repo.conn.rollback()
            self.repo.record_transaction(
                tx_id=tx.id,
                actor_role=tx.actor_role,
                actor_run_id=tx.actor_run_id,
                summary=tx.summary,
                accepted=False,
                payload={"error": exc.code.value, "message": exc.message},
            )
            self.repo.conn.commit()
            return ApplyResult(
                tx_id=tx.id,
                accepted=False,
                rejections=[{"code": exc.code.value, "message": exc.message}],
                affected_node_ids=[],
            )
        except Exception as exc:  # pragma: no cover - safety net
            self.repo.conn.rollback()
            return ApplyResult(
                tx_id=tx.id,
                accepted=False,
                rejections=[{"code": "INTERNAL_ERROR", "message": str(exc)}],
                affected_node_ids=[],
            )

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        obj = self.repo.get_object(node_id)
        return None if obj is None else obj.to_dict()

    def find_frontier(self, limit: int = 20) -> list[dict[str, Any]]:
        return [obj.to_dict() for obj in self.repo.get_frontier(limit)]

    def graph_statistics(self) -> dict[str, Any]:
        objects = self.repo.list_objects(limit=10_000)
        statuses: dict[str, int] = {}
        types: dict[str, int] = {}
        for obj in objects:
            statuses[obj.status] = statuses.get(obj.status, 0) + 1
            types[obj.type] = types.get(obj.type, 0) + 1
        return {
            "object_count": len(objects),
            "statuses": statuses,
            "types": types,
            "math_edge_count": len(self.repo.list_math_edges()),
            "provenance_edge_count": len(self.repo.list_provenance_edges()),
        }

    def history(self, node_id: str) -> list[dict[str, Any]]:
        return self.repo.get_events_for_node(node_id)

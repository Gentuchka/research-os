"""Node and run budget accounting."""

from __future__ import annotations

from typing import Any

from research_os.kernel.types import InvariantCode, KernelError
from research_os.store.repository import Repository


class BudgetService:
    def __init__(self, repo: Repository, config: dict[str, Any]) -> None:
        self.repo = repo
        self.defaults = config.get("defaults", {})

    def consume(
        self,
        *,
        run_id: str,
        node_id: str,
        budget_name: str,
        amount: float = 1.0,
        detail: str | None = None,
    ) -> dict[str, Any]:
        remaining = self.repo.consume_node_budget(node_id, budget_name, amount)
        self.repo.record_budget_usage(run_id, budget_name, amount, detail)
        if remaining < 0:
            raise KernelError(
                InvariantCode.BUDGET_EXHAUSTED,
                f"Budget exhausted for {node_id}:{budget_name}",
            )
        return {"node_id": node_id, "budget_name": budget_name, "remaining": remaining}

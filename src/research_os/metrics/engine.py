"""Metrics computation."""

from __future__ import annotations

from collections import deque
from typing import Any

from research_os.kernel.types import AppendMetricOp, utc_now
from research_os.store.repository import Repository


class MetricsEngine:
    def __init__(self, repo: Repository, frontier_config: dict[str, Any]) -> None:
        self.repo = repo
        self.frontier_config = frontier_config

    def recompute(self, node_ids: list[str]) -> None:
        for node_id in node_ids:
            distance = self._distance_to_main(node_id)
            if distance is not None:
                self._write_metric(node_id, "distance", float(distance))

    def _write_metric(self, node_id: str, name: str, value: float) -> None:
        op = AppendMetricOp(
            node_id=node_id,
            metric_name=name,
            value=value,
            method="metrics_engine",
            version="v1",
        )
        self.repo._append_metric(f"ros_metric_{node_id}", op, utc_now().isoformat())

    def _distance_to_main(self, node_id: str) -> int | None:
        mains = [o.id for o in self.repo.list_objects(limit=10_000) if o.type == "MainConjecture"]
        if not mains:
            return None
        edges = self.repo.list_math_edges()
        graph: dict[str, list[str]] = {}
        for src, dst, _ in edges:
            graph.setdefault(src, []).append(dst)
            graph.setdefault(dst, []).append(src)
        if node_id in mains:
            return 0
        queue = deque([(node_id, 0)])
        seen = {node_id}
        while queue:
            current, dist = queue.popleft()
            for nxt in graph.get(current, []):
                if nxt in seen:
                    continue
                if nxt in mains:
                    return dist + 1
                seen.add(nxt)
                queue.append((nxt, dist + 1))
        return None

    def score_frontier(self, node_id: str) -> float:
        weights = self.frontier_config.get("weights", {})
        importance = self.repo.get_latest_metric(node_id, "importance") or 0.5
        promise = self.repo.get_latest_metric(node_id, "promise") or 0.5
        information_gain = self.repo.get_latest_metric(node_id, "information_gain") or 0.5
        novelty = self.repo.get_latest_metric(node_id, "novelty") or 0.5
        distance = self.repo.get_latest_metric(node_id, "distance") or 0.0
        research_cost = self.repo.get_latest_metric(node_id, "research_cost") or 0.0
        return (
            weights.get("importance", 0.25) * importance
            + weights.get("promise", 0.25) * promise
            + weights.get("information_gain", 0.30) * information_gain
            + weights.get("novelty", 0.10) * novelty
            + weights.get("distance", -0.15) * distance
            + weights.get("research_cost", -0.20) * research_cost
        )

    def ranked_frontier(self, limit: int = 20) -> list[dict[str, Any]]:
        frontier = self.repo.get_frontier(limit=100)
        ranked = sorted(
            frontier,
            key=lambda obj: self.score_frontier(obj.id),
            reverse=True,
        )
        return [obj.to_dict() for obj in ranked[:limit]]

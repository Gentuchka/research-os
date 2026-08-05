"""Metrics computation (P3.3 frontier scoring v2).

Every metric here is derived deterministically from graph structure, budgets,
and report history already stored in SQLite — no LLM calls, no external
network access. This intentionally keeps metrics reproducible and testable
offline.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any

from research_os.anti_slop.embedding import cosine, embed
from research_os.kernel.types import AppendMetricOp, utc_now
from research_os.store.repository import Repository

COMPUTED_METRICS = (
    "distance",
    "importance",
    "promise",
    "novelty",
    "information_gain",
    "research_cost",
    "branching_factor",
    "verification_confidence",
)


class MetricsEngine:
    def __init__(self, repo: Repository, frontier_config: dict[str, Any]) -> None:
        self.repo = repo
        self.frontier_config = frontier_config

    def recompute(self, node_ids: list[str]) -> None:
        all_edges = self.repo.list_math_edges()
        all_objects = self.repo.list_objects(limit=10_000)
        for node_id in node_ids:
            distance = self._distance_to_main(node_id, all_edges)
            if distance is not None:
                self._write_metric(node_id, "distance", float(distance))
            obj = self.repo.get_object(node_id)
            if obj is None:
                continue
            branching = self._branching_factor(node_id, all_edges)
            self._write_metric(node_id, "branching_factor", branching)
            self._write_metric(
                node_id, "importance", self._importance(node_id, distance, all_edges)
            )
            self._write_metric(node_id, "promise", self._promise(node_id))
            self._write_metric(node_id, "novelty", self._novelty(obj, all_objects))
            self._write_metric(
                node_id, "information_gain", self._information_gain(node_id, all_edges)
            )
            self._write_metric(node_id, "research_cost", self._research_cost(node_id))
            self._write_metric(
                node_id, "verification_confidence", self._verification_confidence(obj)
            )

    def set_human_pin(self, node_id: str, weight: float = 1.0) -> None:
        """Record a human priority pin (P3.1 `pin_node`). Metadata only —
        does not mutate the knowledge graph, just biases frontier ranking."""
        self._write_metric(node_id, "human_pin", max(0.0, min(1.0, weight)))

    def _write_metric(self, node_id: str, name: str, value: float) -> None:
        op = AppendMetricOp(
            node_id=node_id,
            metric_name=name,
            value=value,
            method="metrics_engine",
            version="v2",
        )
        self.repo._append_metric(f"ros_metric_{node_id}", op, utc_now().isoformat())

    def _distance_to_main(
        self, node_id: str, edges: list[tuple[str, str, str]] | None = None
    ) -> int | None:
        mains = [o.id for o in self.repo.list_objects(limit=10_000) if o.type == "MainConjecture"]
        if not mains:
            return None
        edges = edges if edges is not None else self.repo.list_math_edges()
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

    def nearest_main_path(self, node_id: str) -> dict[str, Any]:
        """Shortest path from node_id to any MainConjecture (P4.1 `nearest_main`)."""
        mains = {o.id for o in self.repo.list_objects(limit=10_000) if o.type == "MainConjecture"}
        if node_id in mains:
            return {"node_id": node_id, "distance": 0, "path": [node_id]}
        if not mains:
            return {"node_id": node_id, "distance": None, "path": []}
        edges = self.repo.list_math_edges()
        graph: dict[str, list[str]] = {}
        for src, dst, _ in edges:
            graph.setdefault(src, []).append(dst)
            graph.setdefault(dst, []).append(src)
        queue = deque([(node_id, [node_id])])
        seen = {node_id}
        while queue:
            current, path = queue.popleft()
            for nxt in graph.get(current, []):
                if nxt in seen:
                    continue
                new_path = [*path, nxt]
                if nxt in mains:
                    return {"node_id": node_id, "distance": len(new_path) - 1, "path": new_path}
                seen.add(nxt)
                queue.append((nxt, new_path))
        return {"node_id": node_id, "distance": None, "path": []}

    def _branching_factor(self, node_id: str, edges: list[tuple[str, str, str]]) -> float:
        degree = sum(1 for src, dst, _ in edges if src == node_id or dst == node_id)
        return max(0.0, min(1.0, degree / 8.0))

    def _importance(
        self,
        node_id: str,
        distance: int | None,
        edges: list[tuple[str, str, str]],
    ) -> float:
        distance_term = 1.0 / (1.0 + distance) if distance is not None else 0.2
        in_degree = sum(1 for _src, dst, _ in edges if dst == node_id)
        centrality_term = max(0.0, min(1.0, in_degree / 5.0))
        return max(0.0, min(1.0, 0.6 * distance_term + 0.4 * centrality_term))

    def _promise(self, node_id: str) -> float:
        reports = self.repo.list_reports_for_node(node_id)
        if not reports:
            return 0.5
        accepted = 0
        total = 0
        for report in reports:
            decision = self.repo.get_latest_decision(report.id)
            if decision is None:
                continue
            total += 1
            if decision.decision in {"ACCEPT", "PARTIAL_ACCEPT"}:
                accepted += 1
        if total == 0:
            return 0.5
        return max(0.0, min(1.0, accepted / total))

    def _novelty(self, obj: Any, all_objects: list[Any]) -> float:
        others = [o for o in all_objects if o.id != obj.id]
        if not others:
            return 1.0
        vector = embed(obj.statement)
        best = max(cosine(vector, embed(o.statement)) for o in others)
        return max(0.0, min(1.0, 1.0 - best))

    def _information_gain(self, node_id: str, edges: list[tuple[str, str, str]]) -> float:
        neighbor_ids = {dst for src, dst, _ in edges if src == node_id}
        neighbor_ids |= {src for src, dst, _ in edges if dst == node_id}
        if not neighbor_ids:
            return 0.5
        open_statuses = {"CANDIDATE", "ACTIVE", "STUCK"}
        open_count = 0
        for nid in neighbor_ids:
            neighbor = self.repo.get_object(nid)
            if neighbor is not None and neighbor.status in open_statuses:
                open_count += 1
        return max(0.0, min(1.0, open_count / len(neighbor_ids)))

    def _research_cost(self, node_id: str) -> float:
        budget = self.repo.get_budget(node_id)
        if budget is None or float(budget["attempt_budget"]) <= 0:
            return 0.0
        return max(0.0, min(1.0, float(budget["attempt_used"]) / float(budget["attempt_budget"])))

    def _verification_confidence(self, obj: Any) -> float:
        if obj.status in {"PROVED", "DISPROVED"} and obj.evidence_refs:
            return 1.0
        if obj.status in {"PROVED", "DISPROVED"}:
            return 0.6
        return 0.0

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

    def _tie_break_key(self, node_id: str, obj: Any) -> tuple[float, float, float]:
        pin = self.repo.get_latest_metric(node_id, "human_pin") or 0.0
        verification_confidence = (
            self.repo.get_latest_metric(node_id, "verification_confidence") or 0.0
        )
        # ranked_frontier sorts with reverse=True (descending); negate the parsed
        # timestamp so that, all else equal, OLDER nodes still win the tie-break
        # (older_unexplored) even though the overall sort direction is descending.
        try:
            created_ts = datetime.fromisoformat(obj.created_at).timestamp()
        except ValueError:
            created_ts = 0.0
        return (pin, verification_confidence, -created_ts)

    def ranked_frontier(self, limit: int = 20) -> list[dict[str, Any]]:
        frontier = self.repo.get_frontier(limit=100)
        ranked = sorted(
            frontier,
            key=lambda obj: (self.score_frontier(obj.id), self._tie_break_key(obj.id, obj)),
            reverse=True,
        )
        return [obj.to_dict() for obj in ranked[:limit]]

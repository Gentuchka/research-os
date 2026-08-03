"""Obsidian vault projection from canonical store."""

from __future__ import annotations

from pathlib import Path

from research_os.kernel.types import ResearchObject
from research_os.store.repository import Repository

TYPE_DIRS = {
    "MainConjecture": "01_main",
    "Hypothesis": "02_objects/Hypothesis",
    "Lemma": "02_objects/Lemma",
    "Definition": "02_objects/Definition",
    "Technique": "02_objects/Technique",
    "Construction": "02_objects/Construction",
    "Counterexample": "02_objects/Counterexample",
    "Observation": "02_objects/Observation",
    "Proof": "02_objects/Proof",
    "FailedAttempt": "02_objects/FailedAttempt",
    "ResearchQuestion": "02_objects/ResearchQuestion",
    "Experiment": "02_objects/Experiment",
    "Paper": "02_objects/Paper",
    "Report": "03_reports",
    "DeadEnd": "05_dead_ends",
}


class VaultProjector:
    def __init__(self, repo: Repository, vault_dir: Path) -> None:
        self.repo = repo
        self.vault_dir = vault_dir

    def project_nodes(self, node_ids: list[str]) -> list[Path]:
        paths: list[Path] = []
        for node_id in node_ids:
            obj = self.repo.get_object(node_id)
            if obj is None:
                continue
            path = self._write_object_note(obj)
            paths.append(path)
        return paths

    def project_frontier(self) -> Path:
        frontier = self.repo.get_frontier(limit=50)
        path = self.vault_dir / "04_frontier" / "current.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Research frontier", "", "_Generated._", ""]
        if not frontier:
            lines.append("_Empty until ACTIVE nodes exist._")
        else:
            for obj in frontier:
                lines.append(f"- [[{obj.id}|{obj.title}]] ({obj.type})")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def project_report(self, report, decision) -> Path:
        out_dir = self.vault_dir / "03_reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{report.id}.md"
        lines = [
            "---",
            f"ros_id: {report.id}",
            "type: Report",
            f"status: {report.status}",
            f"decision: {decision.decision}",
            f"subject: {report.subject_node_id}",
            "---",
            "",
            f"# Report {report.id}",
            "",
            "## Summary",
            report.payload.get("summary", "_No summary provided._"),
            "",
            "## Information gained",
        ]
        for item in report.payload.get("information_delta", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Claims"])
        for claim in report.payload.get("claims", []):
            tag = " (speculative)" if claim.get("speculative") else ""
            lines.append(f"- {claim.get('text', '')}{tag}")
        if decision.reason_codes:
            lines.extend(["", "## Review outcome"])
            for code in decision.reason_codes:
                lines.append(f"- {code}")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _write_object_note(self, obj: ResearchObject) -> Path:
        rel_dir = TYPE_DIRS.get(obj.type, "02_objects/Other")
        out_dir = self.vault_dir / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{obj.id}.md"
        math_edges = [
            (src, dst, edge)
            for src, dst, edge in self.repo.list_math_edges()
            if src == obj.id or dst == obj.id
        ]
        prov_edges = [
            (src, dst, edge)
            for src, dst, edge in self.repo.list_provenance_edges()
            if src == obj.id or dst == obj.id
        ]
        events = self.repo.get_events_for_node(obj.id)
        body = self._render_note(obj, math_edges, prov_edges, events)
        path.write_text(body, encoding="utf-8")
        return path

    def _render_note(
        self,
        obj: ResearchObject,
        math_edges: list[tuple[str, str, str]],
        prov_edges: list[tuple[str, str, str]],
        events: list[dict],
    ) -> str:
        metrics_rows = self.repo.conn.execute(
            """
            SELECT metric_name, value, method, version, created_at
            FROM metrics WHERE node_id = ?
            ORDER BY id
            """,
            (obj.id,),
        ).fetchall()
        lines = [
            "---",
            f"ros_id: {obj.id}",
            f"type: {obj.type}",
            f"status: {obj.status}",
            f"content_hash: {obj.content_hash}",
            f"created_at: {obj.created_at}",
            f"admitted_at: {obj.admitted_at}",
            f"origin_kind: {obj.provenance.origin_kind}",
            f"origin_refs: {obj.provenance.origin_refs}",
            "tags: []",
            "---",
            "",
            f"# {obj.title}",
            "",
            "## Statement",
            obj.statement,
            "",
            "## Information gain",
            obj.information_gain or "",
            "",
            "## Evidence",
        ]
        if obj.evidence_refs:
            lines.extend(f"- [[{ref}]]" for ref in obj.evidence_refs)
        else:
            lines.append("_None recorded._")
        lines.extend(["", "## Links"])
        if math_edges:
            for src, dst, edge in math_edges:
                if src == obj.id:
                    lines.append(f"- {edge} [[{dst}]]")
                else:
                    lines.append(f"- {edge} from [[{src}]]")
        else:
            lines.append("_No mathematical links._")
        lines.extend(["", "## Provenance"])
        if prov_edges:
            for src, dst, edge in prov_edges:
                lines.append(f"- {edge}: [[{src}]] -> [[{dst}]]")
        else:
            lines.append(
                f"- origin: {obj.provenance.origin_kind} {obj.provenance.origin_refs}"
            )
        lines.extend(["", "## Metrics"])
        if metrics_rows:
            for row in metrics_rows:
                lines.append(
                    f"- {row['metric_name']}: {row['value']} "
                    f"({row['method']} {row['version']} @ {row['created_at']})"
                )
        else:
            lines.append("_No metrics recorded._")
        lines.extend(["", "## History"])
        if events:
            for event in events:
                lines.append(
                    f"- {event['created_at']}: {event['event_type']} "
                    f"({event['transaction_id']})"
                )
        else:
            lines.append("_No events yet._")
        lines.append("")
        return "\n".join(lines)

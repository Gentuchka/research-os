"""Cursor SDK worker adapter for live investigations."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from research_os.agents.worker.model_resolver import ModelResolver
from research_os.agents.worker.sandbox import cleanup_worker_sandbox, create_worker_sandbox
from research_os.config import RuntimeConfig
from research_os.kernel.types import RoleContext
from research_os.reports.intake import ReportIntake
from research_os.reports.types import ResearchReport
from research_os.store.repository import Repository


class CursorSdkWorker:
    def __init__(
        self,
        repo: Repository,
        report_intake: ReportIntake,
        config: RuntimeConfig,
        model_resolver: ModelResolver,
    ) -> None:
        self.repo = repo
        self.report_intake = report_intake
        self.config = config
        self.model_resolver = model_resolver

    def investigate(self, ctx: RoleContext, subject_node_id: str) -> ResearchReport:
        try:
            from cursor_sdk import Agent, CursorAgentError, LocalAgentOptions
        except ImportError as exc:
            raise RuntimeError(
                "cursor-sdk is not installed. Install with: pip install -e '.[sdk]'"
            ) from exc

        api_key = os.environ.get("CURSOR_API_KEY")
        if not api_key:
            raise RuntimeError("CURSOR_API_KEY is required for live Cursor SDK workers")

        resolved = self.model_resolver.resolve_worker_profile()
        sandbox = create_worker_sandbox()
        mcp_command = sys.executable
        mcp_args = ["-m", "research_os.mcp_server.server"]
        mcp_env = {
            **os.environ,
            "RESEARCH_OS_REPO": str(self.config.repo_root),
            "PYTHONPATH": str(self.config.repo_root / "src"),
        }
        prompt = self._build_prompt(subject_node_id, ctx.run_id)
        try:
            self.repo.heartbeat_run(ctx.run_id, f"Launching worker ({resolved.model_id})")
            self.repo.record_budget_usage(ctx.run_id, "model_profile", 1.0, resolved.profile_name)
            self.repo.conn.commit()
            with Agent.create(
                model=resolved.model_id,
                api_key=api_key,
                local=LocalAgentOptions(cwd=str(sandbox), setting_sources=[]),
                mcp_servers={
                    "research-os": {
                        "command": mcp_command,
                        "args": mcp_args,
                        "env": mcp_env,
                    }
                },
            ) as agent:
                run = agent.send(prompt)
                self.repo.heartbeat_run(ctx.run_id, f"SDK run {run.id} in progress")
                self.repo.conn.commit()
                result = run.wait()
                if result.status == "error":
                    raise RuntimeError(f"Cursor SDK run failed: {result.id}")
            existing = self.repo.get_report_for_run(ctx.run_id)
            if existing is not None:
                return existing
            return self._fallback_submit(ctx, subject_node_id, result)
        except CursorAgentError as exc:
            self.repo.fail_run(ctx.run_id, "SDK_STARTUP", str(exc))
            self.repo.conn.commit()
            raise
        finally:
            cleanup_worker_sandbox(sandbox)

    def _build_prompt(self, subject_node_id: str, run_id: str) -> str:
        return (
            "You are a Research OS Worker. Investigate the subject node and submit exactly one "
            "structured worker report via the research-os MCP tool `submit_report`.\n\n"
            f"- role: worker\n"
            f"- run_id: {run_id}\n"
            f"- subject_node_id: {subject_node_id}\n\n"
            "Use MCP read tools (`get_node`, `history`, `find_frontier`) for context. "
            "Do not mutate the knowledge graph directly.\n"
            "The report JSON must follow the worker report schema with fields: report_type, "
            "subject_node_id, summary, information_delta, claims, proposed_objects, "
            "proposed_links, literature_refs, estimated_difficulty, confidence.\n"
            "After calling submit_report, reply with the report id only."
        )

    def _fallback_submit(
        self, ctx: RoleContext, subject_node_id: str, result: Any
    ) -> ResearchReport:
        text = getattr(result, "result", "") or ""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {
                "report_type": "worker",
                "subject_node_id": subject_node_id,
                "summary": "SDK run completed without MCP submit_report",
                "information_delta": [text[:500] or "No structured delta returned"],
                "claims": [{"text": text[:500], "speculative": True}],
                "proposed_objects": [],
                "proposed_links": [],
                "literature_refs": [],
                "estimated_difficulty": 0.5,
                "confidence": 0.2,
            }
        return self.report_intake.submit(ctx, payload)

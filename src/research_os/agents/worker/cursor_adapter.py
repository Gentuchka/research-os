"""Cursor SDK worker adapter for live investigations."""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any

from research_os.agents.worker.model_resolver import ModelResolver
from research_os.agents.worker.sandbox import cleanup_worker_sandbox, create_worker_sandbox
from research_os.config import RuntimeConfig
from research_os.kernel.types import RoleContext
from research_os.reports.intake import ReportIntake
from research_os.reports.types import ResearchReport
from research_os.store.repository import Repository

MAX_STARTUP_RETRIES = 3
HEARTBEAT_INTERVAL_SECONDS = 15


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
        sdk_run: Any = None
        try:
            self.repo.heartbeat_run(ctx.run_id, f"Launching worker ({resolved.model_id})")
            self.repo.record_budget_usage(ctx.run_id, "model_profile", 1.0, resolved.profile_name)
            self.repo.conn.commit()

            agent = None
            for attempt in range(1, MAX_STARTUP_RETRIES + 1):
                try:
                    model_arg: object = (
                        {"id": resolved.model_id, "reasoning_effort": resolved.reasoning_effort}
                        if resolved.reasoning_effort
                        else resolved.model_id
                    )
                    agent = Agent.create(
                        model=model_arg,
                        api_key=api_key,
                        local=LocalAgentOptions(cwd=str(sandbox), setting_sources=[]),
                        mcp_servers={
                            "research-os": {
                                "command": mcp_command,
                                "args": mcp_args,
                                "env": mcp_env,
                            }
                        },
                    )
                    break
                except CursorAgentError as exc:
                    retryable = getattr(exc, "retryable", False)
                    if attempt >= MAX_STARTUP_RETRIES or not retryable:
                        raise
                    delay = getattr(exc, "retry_after_seconds", 1.0)
                    self.repo.heartbeat_run(
                        ctx.run_id,
                        f"SDK startup retry {attempt}/{MAX_STARTUP_RETRIES}",
                    )
                    self.repo.conn.commit()
                    time.sleep(delay)

            if agent is None:
                raise RuntimeError("Failed to create Cursor SDK agent")

            with agent:
                sdk_run = agent.send(prompt)
                self.repo.persist_sdk_ids(ctx.run_id, str(agent.id), str(sdk_run.id))
                self.repo.heartbeat_run(ctx.run_id, f"SDK run {sdk_run.id} in progress")
                self.repo.conn.commit()
                last_heartbeat = time.monotonic()
                for message in sdk_run.messages():
                    if message.type == "assistant":
                        summary = self._sanitize_summary(getattr(message, "text", "") or "")
                        self.repo.heartbeat_run(ctx.run_id, summary or "Assistant produced output")
                        self.repo.conn.commit()
                    if time.monotonic() - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                        self.repo.heartbeat_run(ctx.run_id, "Worker heartbeat")
                        self.repo.conn.commit()
                        last_heartbeat = time.monotonic()
                result = sdk_run.wait()
                if result.status == "error":
                    self.repo.fail_run(
                        ctx.run_id, "SDK_RUN", f"Cursor SDK run failed: {result.id}"
                    )
                    self.repo.conn.commit()
                    raise RuntimeError(f"Cursor SDK run failed: {result.id}")

            existing = self.repo.get_report_for_run(ctx.run_id)
            if existing is not None:
                return existing
            raise RuntimeError(
                "Live worker must submit a report via MCP submit_report; no fallback allowed"
            )
        except CursorAgentError as exc:
            self.repo.fail_run(ctx.run_id, "SDK_STARTUP", str(exc))
            self.repo.conn.commit()
            raise
        finally:
            cleanup_worker_sandbox(sandbox)

    def _sanitize_summary(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) > 120:
            return cleaned[:117] + "..."
        return cleaned

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

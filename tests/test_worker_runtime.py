"""Worker sandbox and model resolver tests."""

from __future__ import annotations

from research_os.agents.worker.model_resolver import ModelResolver
from research_os.agents.worker.sandbox import cleanup_worker_sandbox, create_worker_sandbox


def test_worker_sandbox_has_deny_hooks():
    sandbox = create_worker_sandbox()
    try:
        hooks = sandbox / ".cursor" / "hooks.json"
        assert hooks.exists()
        text = hooks.read_text(encoding="utf-8")
        assert "beforeShellExecution" in text
        assert "beforeReadFile" in text
        assert "beforeMCPExecution" in text
        assert (sandbox / ".cursor" / "hooks" / "deny_shell.py").exists()
    finally:
        cleanup_worker_sandbox(sandbox)


def test_model_resolver_uses_configured_profile(runtime):
    resolver = ModelResolver(runtime)
    resolved = resolver.resolve_worker_profile()
    assert resolved.profile_name == "gpt56_sol_high"
    assert resolved.model_id

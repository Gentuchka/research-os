"""Isolated per-run worker sandbox with fail-closed Cursor hooks."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

HOOKS_JSON = """{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [
      {
        "command": ".cursor/hooks/deny_shell.py",
        "failClosed": true
      }
    ],
    "beforeReadFile": [
      {
        "command": ".cursor/hooks/deny_read.py",
        "failClosed": true
      }
    ],
    "preToolUse": [
      {
        "command": ".cursor/hooks/deny_write_tools.py",
        "matcher": "Write|Edit|Delete|ApplyPatch",
        "failClosed": true
      }
    ],
    "beforeMCPExecution": [
      {
        "command": ".cursor/hooks/allow_research_mcp.py",
        "failClosed": true
      }
    ]
  }
}
"""

DENY_SHELL = """import json
print(json.dumps({
    "permission": "deny",
    "agent_message": (
        "Shell execution is disabled in the Research OS worker sandbox. "
        "Use Research MCP tools only."
    ),
}))
"""

DENY_READ = """import json
print(json.dumps({
    "permission": "deny",
    "agent_message": (
        "Filesystem reads are disabled in the Research OS worker sandbox. "
        "Use Research MCP tools only."
    ),
}))
"""

DENY_WRITE = """import json
print(json.dumps({
    "permission": "deny",
    "agent_message": (
        "Filesystem writes are disabled in the Research OS worker sandbox. "
        "Use Research MCP tools only."
    ),
}))
"""

ALLOW_RESEARCH_MCP = """import json, sys
payload = json.load(sys.stdin)
server = (payload.get("server") or payload.get("mcpServer") or "").lower()
tool_name = (payload.get("tool") or payload.get("toolName") or "").lower()
if "research" in server or tool_name.startswith("submit_report") or tool_name.startswith("get_"):
    print(json.dumps({"permission": "allow"}))
else:
    print(json.dumps({
        "permission": "deny",
        "agent_message": "Only the Research OS MCP server is allowed in worker sandboxes."
    }))
"""


def create_worker_sandbox() -> Path:
    root = Path(tempfile.mkdtemp(prefix="ros_worker_"))
    hooks_dir = root / ".cursor" / "hooks"
    hooks_dir.mkdir(parents=True)
    (root / ".cursor" / "hooks.json").write_text(HOOKS_JSON, encoding="utf-8")
    (hooks_dir / "deny_shell.py").write_text(DENY_SHELL, encoding="utf-8")
    (hooks_dir / "deny_read.py").write_text(DENY_READ, encoding="utf-8")
    (hooks_dir / "deny_write_tools.py").write_text(DENY_WRITE, encoding="utf-8")
    (hooks_dir / "allow_research_mcp.py").write_text(ALLOW_RESEARCH_MCP, encoding="utf-8")
    readme = root / "README.md"
    readme.write_text(
        "# Research worker sandbox\n\n"
        "This directory is intentionally empty. Interact with Research OS only via MCP.\n",
        encoding="utf-8",
    )
    return root


def cleanup_worker_sandbox(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)

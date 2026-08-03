"""Role-based MCP tool access control."""

from __future__ import annotations

from typing import Any

from research_os.kernel.types import InvariantCode, KernelError, RoleContext


class ACL:
    def __init__(self, roles_config: dict[str, Any]) -> None:
        self.roles_config = roles_config

    def assert_tool(self, ctx: RoleContext, tool_name: str) -> None:
        role_cfg = self.roles_config.get("roles", {}).get(ctx.role.value)
        if role_cfg is None:
            raise KernelError(InvariantCode.ACL_DENIED, f"Unknown role: {ctx.role.value}")
        deny = set(role_cfg.get("deny", []))
        if tool_name in deny:
            raise KernelError(
                InvariantCode.ACL_DENIED,
                f"Role {ctx.role.value} denied tool {tool_name}",
            )
        tools = role_cfg.get("tools")
        if tools == "all":
            return
        if isinstance(tools, list) and tool_name not in tools:
            raise KernelError(
                InvariantCode.ACL_DENIED,
                f"Role {ctx.role.value} lacks tool {tool_name}",
            )

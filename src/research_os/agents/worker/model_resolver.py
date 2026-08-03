"""Resolve and validate model profiles against Cursor SDK discovery."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from research_os.config import RuntimeConfig


@dataclass(frozen=True)
class ResolvedModel:
    profile_name: str
    model_id: str
    reasoning_effort: str | None = None


class ModelResolver:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def resolve_worker_profile(self) -> ResolvedModel:
        roles = self.config.models_config.get("roles", {})
        override = self.config.models_config.get("run_override", {}).get("profile")
        profile_name = override or roles.get("worker", {}).get("profile", "gpt56_sol_high")
        profile = self.config.models_config.get("profiles", {}).get(profile_name)
        if profile is None:
            raise ValueError(f"Unknown model profile: {profile_name}")
        model_id = str(profile.get("model", "composer-2.5"))
        reasoning = profile.get("reasoning_effort")
        validated_id = self._validate_model_id(model_id)
        return ResolvedModel(
            profile_name=profile_name,
            model_id=validated_id,
            reasoning_effort=reasoning,
        )

    def _validate_model_id(self, configured_id: str) -> str:
        api_key = os.environ.get("CURSOR_API_KEY")
        if not api_key:
            return configured_id
        try:
            from cursor_sdk import Cursor
        except ImportError:
            return configured_id
        available = {m.id for m in Cursor.models.list(api_key=api_key)}
        if configured_id in available:
            return configured_id
        # Fall back to a known-good default when placeholder YAML IDs are stale.
        for candidate in ("composer-2.5", "gpt-5.6-sol-medium", "auto"):
            if candidate in available:
                return candidate
        if available:
            return sorted(available)[0]
        return configured_id

    def profile_summary(self, resolved: ResolvedModel) -> dict[str, Any]:
        return {
            "profile": resolved.profile_name,
            "model_id": resolved.model_id,
            "reasoning_effort": resolved.reasoning_effort,
        }

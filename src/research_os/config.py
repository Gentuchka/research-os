"""Runtime configuration loaded from repo root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
SCHEMAS_DIR = REPO_ROOT / "schemas"
VAULT_DIR = REPO_ROOT / "vault"
DATA_DIR = REPO_ROOT / "data"
CANONICAL_DB = DATA_DIR / "canonical" / "research.db"
TRANSACTIONS_DIR = DATA_DIR / "transactions"
REJECTIONS_DIR = DATA_DIR / "rejections"


@dataclass(frozen=True)
class RuntimeConfig:
    repo_root: Path
    db_path: Path
    vault_dir: Path
    transactions_dir: Path
    rejections_dir: Path
    roles_config: dict[str, Any]
    anti_slop_config: dict[str, Any]
    frontier_config: dict[str, Any]
    budgets_config: dict[str, Any]
    models_config: dict[str, Any]
    activity_config: dict[str, Any]
    git_commit_enabled: bool = True
    strict_git_commit: bool = False

    @classmethod
    def load(
        cls,
        repo_root: Path | None = None,
        *,
        git_commit_enabled: bool = True,
        strict_git_commit: bool = False,
    ) -> RuntimeConfig:
        root = repo_root or Path(os.environ.get("RESEARCH_OS_REPO", str(REPO_ROOT)))
        configs = root / "configs"
        return cls(
            repo_root=root,
            db_path=root / "data" / "canonical" / "research.db",
            vault_dir=root / "vault",
            transactions_dir=root / "data" / "transactions",
            rejections_dir=root / "data" / "rejections",
            roles_config=load_yaml(configs / "roles.yaml"),
            anti_slop_config=load_yaml(configs / "anti_slop.yaml"),
            frontier_config=load_yaml(configs / "frontier.yaml"),
            budgets_config=load_yaml(configs / "budgets.yaml"),
            models_config=load_yaml(configs / "models.yaml"),
            activity_config=load_yaml(configs / "activity.yaml")
            if (configs / "activity.yaml").exists()
            else {"heartbeat_stale_seconds": 120, "refresh_throttle_seconds": 5},
            git_commit_enabled=git_commit_enabled,
            strict_git_commit=strict_git_commit,
        )


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)

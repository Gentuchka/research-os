"""Runtime configuration loaded from repo root."""

from __future__ import annotations

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


@dataclass(frozen=True)
class RuntimeConfig:
    repo_root: Path
    db_path: Path
    vault_dir: Path
    transactions_dir: Path
    roles_config: dict[str, Any]
    git_commit_enabled: bool = True

    @classmethod
    def load(
        cls,
        repo_root: Path | None = None,
        *,
        git_commit_enabled: bool = True,
    ) -> RuntimeConfig:
        root = repo_root or REPO_ROOT
        roles_path = root / "configs" / "roles.yaml"
        with roles_path.open(encoding="utf-8") as fh:
            roles_config = yaml.safe_load(fh)
        return cls(
            repo_root=root,
            db_path=root / "data" / "canonical" / "research.db",
            vault_dir=root / "vault",
            transactions_dir=root / "data" / "transactions",
            roles_config=roles_config,
            git_commit_enabled=git_commit_enabled,
        )


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)

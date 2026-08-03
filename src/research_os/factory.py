"""Factory for constructing services without MCP global state."""

from __future__ import annotations

from research_os.config import RuntimeConfig
from research_os.kernel.transaction_service import TransactionService
from research_os.projection.vault import VaultProjector
from research_os.store.connection import connect
from research_os.store.repository import Repository


def build_service(config: RuntimeConfig) -> TransactionService:
    conn = connect(config.db_path)
    repo = Repository(conn)
    projector = VaultProjector(repo, config.vault_dir)
    return TransactionService(repo, config, projector)

"""Backup and recovery (P7.2).

Online SQLite snapshot (via the stdlib `sqlite3.Connection.backup` API, so it
is safe to run against a live database) plus a manifest of vault files, and an
optional portable JSONL export of the canonical graph.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_os.config import RuntimeConfig
from research_os.store.repository import Repository


class BackupService:
    def __init__(self, repo: Repository, config: RuntimeConfig) -> None:
        self.repo = repo
        self.config = config

    def backup(self, backup_root: Path) -> Path:
        """Snapshot the canonical DB + a manifest of vault files under
        `backup_root/backup_<timestamp>/`. Returns the snapshot directory."""
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snapshot_dir = backup_root / f"backup_{timestamp}"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        dst_conn = sqlite3.connect(str(snapshot_dir / "research.db"))
        try:
            self.repo.conn.backup(dst_conn)
        finally:
            dst_conn.close()

        vault_dir = self.config.vault_dir
        vault_files = sorted(
            str(p.relative_to(vault_dir).as_posix())
            for p in vault_dir.rglob("*")
            if p.is_file()
        )
        manifest = {
            "created_at": datetime.now(UTC).isoformat(),
            "db_file": "research.db",
            "vault_dir": str(vault_dir),
            "vault_file_count": len(vault_files),
            "vault_files": vault_files,
        }
        (snapshot_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return snapshot_dir

    def restore(self, snapshot_dir: Path, *, force: bool = False) -> Path:
        """Restore the canonical DB from a snapshot directory produced by
        `backup()`. Refuses to overwrite an existing DB unless force=True."""
        src_db = snapshot_dir / "research.db"
        if not src_db.exists():
            raise FileNotFoundError(f"No research.db found in snapshot: {snapshot_dir}")
        if self.config.db_path.exists() and not force:
            raise FileExistsError(
                f"{self.config.db_path} already exists; pass force=True to overwrite"
            )
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        src_conn = sqlite3.connect(str(src_db))
        try:
            dst_conn = sqlite3.connect(str(self.config.db_path))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
        return self.config.db_path

    def export_jsonl(self, path: Path) -> Path:
        """Optional (P7.2): portable JSONL export of the canonical graph
        (objects + math/provenance edges) for archival outside SQLite."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for obj in self.repo.list_objects(limit=1_000_000):
                self._write_line(fh, {"record_type": "object", **obj.to_dict()})
            for src, dst, edge in self.repo.list_math_edges():
                self._write_line(
                    fh,
                    {"record_type": "math_edge", "from_id": src, "to_id": dst, "edge_type": edge},
                )
            for src, dst, edge in self.repo.list_provenance_edges():
                self._write_line(
                    fh,
                    {
                        "record_type": "provenance_edge",
                        "from_id": src,
                        "to_id": dst,
                        "edge_type": edge,
                    },
                )
        return path

    @staticmethod
    def _write_line(fh: Any, record: dict[str, Any]) -> None:
        fh.write(json.dumps(record) + "\n")

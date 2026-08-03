"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from research_os.store.migrations import migrate


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn

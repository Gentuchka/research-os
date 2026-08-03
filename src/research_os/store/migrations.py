"""SQLite schema migrations."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS objects (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        statement TEXT NOT NULL,
        formalization TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        admitted_at TEXT,
        content_hash TEXT NOT NULL UNIQUE,
        equivalence_class_id TEXT,
        is_class_representative INTEGER NOT NULL DEFAULT 1,
        provenance_json TEXT NOT NULL,
        evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        tags_json TEXT NOT NULL DEFAULT '[]',
        information_gain TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS object_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_id TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        admitted_at TEXT NOT NULL,
        transaction_id TEXT NOT NULL,
        UNIQUE(object_id, content_hash)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS math_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_id TEXT NOT NULL,
        to_id TEXT NOT NULL,
        edge_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        transaction_id TEXT NOT NULL,
        UNIQUE(from_id, to_id, edge_type)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS provenance_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_id TEXT NOT NULL,
        to_id TEXT NOT NULL,
        edge_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        transaction_id TEXT NOT NULL,
        UNIQUE(from_id, to_id, edge_type)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS equivalence_classes (
        id TEXT PRIMARY KEY,
        representative_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        transaction_id TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        transaction_id TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        value REAL NOT NULL,
        method TEXT NOT NULL,
        version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        transaction_id TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS budgets (
        node_id TEXT PRIMARY KEY,
        attempt_budget INTEGER NOT NULL,
        token_budget INTEGER NOT NULL,
        time_budget_seconds INTEGER NOT NULL,
        tool_budget INTEGER NOT NULL,
        branch_budget INTEGER NOT NULL,
        attempt_used INTEGER NOT NULL DEFAULT 0,
        token_used INTEGER NOT NULL DEFAULT 0,
        time_used_seconds INTEGER NOT NULL DEFAULT 0,
        tool_used INTEGER NOT NULL DEFAULT 0,
        branch_used INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        actor_role TEXT NOT NULL,
        actor_run_id TEXT NOT NULL,
        summary TEXT NOT NULL,
        created_at TEXT NOT NULL,
        accepted INTEGER NOT NULL,
        git_commit_sha TEXT,
        payload_json TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_math_edges_from ON math_edges(from_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_math_edges_to ON math_edges(to_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_objects_status ON objects(status);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_objects_type ON objects(type);
    """,
]


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript("\n".join(MIGRATIONS))
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()

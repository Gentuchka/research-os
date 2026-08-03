"""Migration upgrade tests."""

from __future__ import annotations

import sqlite3

from research_os.store.migrations import SCHEMA_VERSION, migrate


def test_fresh_db_migrates_to_latest():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate(conn)
    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "reports" in tables
    assert "agent_runs" in tables
    assert "run_budget_usage" in tables


def test_v1_db_upgrades_to_latest(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE schema_version (version INTEGER NOT NULL)"
    )
    conn.execute("INSERT INTO schema_version(version) VALUES (1)")
    conn.execute(
        """
        CREATE TABLE objects (
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
        """
    )
    conn.execute(
        """
        CREATE TABLE transactions (
            id TEXT PRIMARY KEY,
            actor_role TEXT NOT NULL,
            actor_run_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL,
            accepted INTEGER NOT NULL,
            git_commit_sha TEXT,
            payload_json TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(transactions)").fetchall()
    }
    assert "projection_status" in cols

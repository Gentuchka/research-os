"""SQLite schema migrations."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 5

V1_TABLES: list[str] = [
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
        transaction_id TEXT NOT NULL,
        node_id TEXT
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
        projection_status TEXT,
        payload_json TEXT NOT NULL
    );
    """,
]

V1_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_math_edges_from ON math_edges(from_id);",
    "CREATE INDEX IF NOT EXISTS idx_math_edges_to ON math_edges(to_id);",
    "CREATE INDEX IF NOT EXISTS idx_objects_status ON objects(status);",
    "CREATE INDEX IF NOT EXISTS idx_objects_type ON objects(type);",
    "CREATE INDEX IF NOT EXISTS idx_events_node_id ON events(node_id);",
]

V2_TABLES: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY,
        report_type TEXT NOT NULL,
        subject_node_id TEXT NOT NULL,
        status TEXT NOT NULL,
        run_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS review_decisions (
        id TEXT PRIMARY KEY,
        report_id TEXT NOT NULL,
        decision TEXT NOT NULL,
        reason_codes_json TEXT NOT NULL,
        reviewer_run_id TEXT NOT NULL,
        transaction_id TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS review_queue (
        id TEXT PRIMARY KEY,
        report_id TEXT NOT NULL UNIQUE,
        worker_run_id TEXT NOT NULL,
        reviewer_run_id TEXT,
        status TEXT NOT NULL,
        enqueued_at TEXT NOT NULL,
        decided_at TEXT
    );
    """,
]

V3_TABLES: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        node_id TEXT NOT NULL,
        status TEXT NOT NULL,
        priority REAL NOT NULL DEFAULT 0,
        assigned_run_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_runs (
        id TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        status TEXT NOT NULL,
        node_scope TEXT,
        task_label TEXT,
        model_profile TEXT,
        started_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        ended_at TEXT,
        last_result_summary TEXT,
        error_code TEXT,
        error_message TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        summary TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS run_budget_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        budget_name TEXT NOT NULL,
        amount REAL NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL
    );
    """,
]


def _current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    version_row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    return 0 if version_row is None else int(version_row[0])


def migrate(conn: sqlite3.Connection) -> None:
    version = _current_version(conn)
    if version == 0:
        for stmt in V1_TABLES:
            conn.execute(stmt)
        for stmt in V1_INDEXES:
            conn.execute(stmt)
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (1,))
        version = 1
    if version < 2:
        for stmt in V2_TABLES:
            conn.execute(stmt)
        try:
            conn.execute("ALTER TABLE transactions ADD COLUMN projection_status TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE events ADD COLUMN node_id TEXT")
        except sqlite3.OperationalError:
            pass
        conn.execute("UPDATE schema_version SET version = 2")
        version = 2
    if version < 3:
        for stmt in V3_TABLES:
            conn.execute(stmt)
        conn.execute("UPDATE schema_version SET version = 3")
        version = 3
    if version < 4:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_budget_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                budget_name TEXT NOT NULL,
                amount REAL NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute("UPDATE schema_version SET version = 4")
        version = 4
    if version < 5:
        _migrate_v5(conn)
        conn.execute("UPDATE schema_version SET version = 5")
    conn.commit()


def _migrate_v5(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS report_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            claim_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            speculative INTEGER NOT NULL DEFAULT 0,
            evidence_refs_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            UNIQUE(report_id, claim_index),
            FOREIGN KEY(report_id) REFERENCES reports(id)
        );

        CREATE TABLE IF NOT EXISTS citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            ref TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(report_id) REFERENCES reports(id)
        );

        CREATE TABLE IF NOT EXISTS candidate_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            op_index INTEGER NOT NULL,
            op_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(report_id, op_index),
            FOREIGN KEY(report_id) REFERENCES reports(id)
        );
        """
    )
    for stmt in (
        "ALTER TABLE review_decisions ADD COLUMN accepted_claim_indices_json TEXT",
        "ALTER TABLE review_decisions ADD COLUMN rejected_claim_indices_json TEXT",
        "ALTER TABLE agent_runs ADD COLUMN reasoning_effort TEXT",
        "ALTER TABLE agent_runs ADD COLUMN resolved_model_id TEXT",
        "ALTER TABLE reports ADD COLUMN content_fingerprint TEXT",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.execute(
        """
        UPDATE agent_runs SET status = 'RUNNING'
        WHERE status IN ('running', 'RUNNING')
        """
    )
    conn.execute(
        """
        UPDATE agent_runs SET status = 'FINISHED'
        WHERE status IN ('completed', 'FINISHED')
        """
    )
    conn.execute(
        """
        UPDATE agent_runs SET status = 'FAILED'
        WHERE status IN ('failed', 'FAILED')
        """
    )
    conn.execute(
        """
        UPDATE jobs SET status = 'QUEUED'
        WHERE status IN ('queued', 'pending')
        """
    )

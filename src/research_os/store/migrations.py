"""SQLite schema migrations."""

from __future__ import annotations

import json
import sqlite3

from research_os.kernel.types import canonical_content_hash

SCHEMA_VERSION = 6

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
        version = 5
    if version < 6:
        _migrate_v6(conn)
        conn.execute("UPDATE schema_version SET version = 6")
    conn.commit()


def _report_fingerprint_from_payload(payload: dict) -> str:
    normalized = {
        "subject_node_id": payload["subject_node_id"],
        "information_delta": sorted(payload.get("information_delta", [])),
        "claims": [c.get("text", "") for c in payload.get("claims", [])],
    }
    return canonical_content_hash(normalized)


def _backfill_report_entities(conn: sqlite3.Connection, report_id: str, payload: dict) -> None:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM report_claims WHERE report_id = ?",
        (report_id,),
    ).fetchone()
    if row and int(row["count"]) > 0:
        return
    now = payload.get("created_at") or "1970-01-01T00:00:00"
    for idx, claim in enumerate(payload.get("claims", [])):
        conn.execute(
            """
            INSERT OR IGNORE INTO report_claims(
                report_id, claim_index, claim_id, text, speculative,
                evidence_refs_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                idx,
                claim.get("id", f"claim_{idx}"),
                claim.get("text", ""),
                int(bool(claim.get("speculative"))),
                json.dumps(claim.get("evidence_refs", [])),
                now,
            ),
        )
    for ref in payload.get("literature_refs", []):
        conn.execute(
            "INSERT OR IGNORE INTO citations(report_id, ref, created_at) VALUES (?, ?, ?)",
            (report_id, ref, now),
        )
    op_index = 0
    for proposed in payload.get("proposed_objects", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO candidate_operations(
                report_id, op_index, op_type, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (report_id, op_index, "append_node", json.dumps(proposed), now),
        )
        op_index += 1
    for link in payload.get("proposed_links", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO candidate_operations(
                report_id, op_index, op_type, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (report_id, op_index, "create_link", json.dumps(link), now),
        )
        op_index += 1


def _migrate_v6(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    for stmt in (
        "ALTER TABLE agent_runs ADD COLUMN sdk_agent_id TEXT",
        "ALTER TABLE agent_runs ADD COLUMN sdk_run_id TEXT",
        "ALTER TABLE report_claims ADD COLUMN claim_id TEXT",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass

    rows = conn.execute("SELECT id, payload_json, content_fingerprint FROM reports").fetchall()
    for row in rows:
        payload = json.loads(row["payload_json"])
        fingerprint = row["content_fingerprint"] or _report_fingerprint_from_payload(payload)
        if not row["content_fingerprint"]:
            conn.execute(
                "UPDATE reports SET content_fingerprint = ? WHERE id = ?",
                (fingerprint, row["id"]),
            )
        _backfill_report_entities(conn, row["id"], payload)

    review_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='review_decisions'"
    ).fetchone()
    if review_table is not None:
        conn.execute(
            """
            UPDATE reports SET status = 'NEEDS_HUMAN'
            WHERE status = 'PENDING'
            AND id IN (
                SELECT report_id FROM review_decisions WHERE decision = 'NEEDS_HUMAN'
            )
            """
        )

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_runs_v6 (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL CHECK(role IN ('worker','reviewer','thinker','scheduler','human')),
            status TEXT NOT NULL CHECK(
                status IN (
                    'QUEUED','STARTING','RUNNING','WAITING_FOR_REVIEW',
                    'REVIEWING','FINISHED','FAILED','CANCELLED'
                )
            ),
            node_scope TEXT,
            task_label TEXT,
            model_profile TEXT,
            reasoning_effort TEXT,
            resolved_model_id TEXT,
            sdk_agent_id TEXT,
            sdk_run_id TEXT,
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            ended_at TEXT,
            last_result_summary TEXT,
            error_code TEXT,
            error_message TEXT
        );
        INSERT OR IGNORE INTO agent_runs_v6
        SELECT
            id, role, status, node_scope, task_label, model_profile,
            reasoning_effort, resolved_model_id, sdk_agent_id, sdk_run_id,
            started_at, updated_at, ended_at, last_result_summary,
            error_code, error_message
        FROM agent_runs;
        DROP TABLE agent_runs;
        ALTER TABLE agent_runs_v6 RENAME TO agent_runs;

        CREATE TABLE IF NOT EXISTS jobs_v6 (
            id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK(
                status IN (
                    'QUEUED','STARTING','RUNNING','WAITING_FOR_REVIEW',
                    'REVIEWING','FINISHED','FAILED','CANCELLED'
                )
            ),
            priority REAL NOT NULL DEFAULT 0,
            assigned_run_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT OR IGNORE INTO jobs_v6
        SELECT id, node_id, status, priority, assigned_run_id, created_at, updated_at
        FROM jobs;
        DROP TABLE jobs;
        ALTER TABLE jobs_v6 RENAME TO jobs;

        CREATE TABLE IF NOT EXISTS reports_v6 (
            id TEXT PRIMARY KEY,
            report_type TEXT NOT NULL CHECK(report_type IN ('worker','thinker','human')),
            subject_node_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK(
                status IN (
                    'PENDING','IN_REVIEW','NEEDS_HUMAN','ACCEPTED',
                    'PARTIAL','REJECTED'
                )
            ),
            run_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            content_fingerprint TEXT
        );
        INSERT OR IGNORE INTO reports_v6
        SELECT id, report_type, subject_node_id, status, run_id, payload_json,
               created_at, content_fingerprint
        FROM reports;
        DROP TABLE reports;
        ALTER TABLE reports_v6 RENAME TO reports;
        """
    )
    conn.execute("PRAGMA foreign_keys = ON")


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

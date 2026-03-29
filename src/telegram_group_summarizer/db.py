from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import AppConfig, load_config
from .models import NormalizedMessage, ResolvedTarget

MIGRATION_VERSION = "0001_initial"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_db(db_path: Path, busy_timeout_ms: int) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    return connection


def ensure_database(config: Optional[AppConfig] = None) -> sqlite3.Connection:
    app_config = config or load_config()
    connection = connect_db(app_config.db_path, app_config.sqlite_busy_timeout_ms)
    apply_migrations(connection)
    return connection


def apply_migrations(connection: sqlite3.Connection) -> None:
    migration_sql = (
        files("telegram_group_summarizer").joinpath("migrations/0001_initial.sql").read_text()
    )
    connection.executescript(migration_sql)
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, ?)",
        (MIGRATION_VERSION, utc_now()),
    )
    connection.commit()


def get_target_by_key(connection: sqlite3.Connection, target_key: str) -> Optional[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM report_targets WHERE target_key = ?",
        (target_key,),
    ).fetchone()


def upsert_report_target(connection: sqlite3.Connection, resolved_target: ResolvedTarget) -> int:
    now = utc_now()
    existing = get_target_by_key(connection, resolved_target.target_key)
    if existing:
        connection.execute(
            """
            UPDATE report_targets
            SET telegram_entity_id = ?, telegram_entity_type = ?, display_name = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                resolved_target.entity_id,
                resolved_target.entity_type,
                resolved_target.display_name,
                now,
                existing["id"],
            ),
        )
        connection.commit()
        return int(existing["id"])

    cursor = connection.execute(
        """
        INSERT INTO report_targets(
            target_key,
            telegram_entity_id,
            telegram_entity_type,
            display_name,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            resolved_target.target_key,
            resolved_target.entity_id,
            resolved_target.entity_type,
            resolved_target.display_name,
            now,
            now,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def create_collection_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    target_id: int,
    lookback_hours: int,
    status: str = "started",
) -> None:
    connection.execute(
        """
        INSERT INTO collection_runs(run_id, target_id, started_at, status, lookback_hours)
        VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, target_id, utc_now(), status, lookback_hours),
    )
    connection.commit()


def update_run_status(
    connection: sqlite3.Connection,
    run_id: str,
    *,
    status: str,
    mode: Optional[str] = None,
    message_count: Optional[int] = None,
    error_summary: Optional[str] = None,
    resolved_target: Optional[ResolvedTarget] = None,
    completed: bool = False,
    report_output_path: Optional[str] = None,
    read_marked: bool = False,
    raw_purged: bool = False,
) -> None:
    run = get_run(connection, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} does not exist.")

    values: Dict[str, object] = {
        "status": status,
        "mode": mode if mode is not None else run["mode"],
        "message_count": message_count if message_count is not None else run["message_count"],
        "error_summary": error_summary if error_summary is not None else run["error_summary"],
        "resolved_entity_id": run["resolved_entity_id"],
        "resolved_entity_type": run["resolved_entity_type"],
        "resolved_entity_display_name": run["resolved_entity_display_name"],
        "completed_at": utc_now() if completed else run["completed_at"],
        "report_output_path": report_output_path
        if report_output_path is not None
        else run["report_output_path"],
        "read_marked_at": utc_now()
        if read_marked and run["read_marked_at"] is None
        else run["read_marked_at"],
        "raw_purged_at": utc_now()
        if raw_purged and run["raw_purged_at"] is None
        else run["raw_purged_at"],
        "run_id": run_id,
    }
    if resolved_target is not None:
        values["resolved_entity_id"] = resolved_target.entity_id
        values["resolved_entity_type"] = resolved_target.entity_type
        values["resolved_entity_display_name"] = resolved_target.display_name

    connection.execute(
        """
        UPDATE collection_runs
        SET status = :status,
            mode = :mode,
            message_count = :message_count,
            error_summary = :error_summary,
            resolved_entity_id = :resolved_entity_id,
            resolved_entity_type = :resolved_entity_type,
            resolved_entity_display_name = :resolved_entity_display_name,
            completed_at = :completed_at,
            report_output_path = :report_output_path,
            read_marked_at = :read_marked_at,
            raw_purged_at = :raw_purged_at
        WHERE run_id = :run_id
        """,
        values,
    )
    connection.commit()


def insert_raw_messages(
    connection: sqlite3.Connection, messages: Iterable[NormalizedMessage]
) -> int:
    rows = list(messages)
    if not rows:
        return 0

    before_changes = connection.total_changes
    connection.executemany(
        """
        INSERT OR IGNORE INTO raw_messages(
            run_id,
            target_id,
            telegram_message_id,
            message_timestamp,
            sender_id,
            sender_name,
            text_content,
            reply_to_message_id,
            forward_source,
            has_links,
            has_media,
            media_kind,
            edited_at,
            is_service_message,
            raw_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.run_id,
                row.target_id,
                row.telegram_message_id,
                row.message_timestamp.isoformat(),
                row.sender_id,
                row.sender_name,
                row.text_content,
                row.reply_to_message_id,
                row.forward_source,
                int(row.has_links),
                int(row.has_media),
                row.media_kind,
                row.edited_at.isoformat() if row.edited_at else None,
                int(row.is_service_message),
                row.raw_json,
                utc_now(),
            )
            for row in rows
        ],
    )
    inserted = connection.total_changes - before_changes
    connection.commit()
    return inserted


def list_raw_messages(connection: sqlite3.Connection, run_id: str) -> List[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM raw_messages
        WHERE run_id = ?
        ORDER BY message_timestamp ASC, telegram_message_id ASC
        """,
        (run_id,),
    ).fetchall()


def get_run(connection: sqlite3.Connection, run_id: str) -> Optional[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM collection_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()


def get_run_with_target(connection: sqlite3.Connection, run_id: str) -> Optional[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            r.*,
            t.target_key,
            t.telegram_entity_id,
            t.telegram_entity_type,
            t.display_name AS target_display_name
        FROM collection_runs r
        JOIN report_targets t ON t.id = r.target_id
        WHERE r.run_id = ?
        """,
        (run_id,),
    ).fetchone()


def create_generated_report(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    target_id: int,
    report_markdown: str,
    output_path: Optional[str] = None,
) -> None:
    connection.execute(
        """
        INSERT INTO generated_reports(run_id, target_id, report_markdown, output_path, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            report_markdown = excluded.report_markdown,
            output_path = excluded.output_path,
            created_at = excluded.created_at
        """,
        (run_id, target_id, report_markdown, output_path, utc_now()),
    )
    update_run_status(
        connection,
        run_id,
        status="summarized",
        completed=False,
        report_output_path=output_path,
    )


def get_generated_report(connection: sqlite3.Connection, run_id: str) -> Optional[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM generated_reports WHERE run_id = ?",
        (run_id,),
    ).fetchone()


def delete_raw_messages(connection: sqlite3.Connection, run_id: str) -> int:
    cursor = connection.execute("DELETE FROM raw_messages WHERE run_id = ?", (run_id,))
    connection.commit()
    return cursor.rowcount


def count_raw_messages(connection: sqlite3.Connection, run_id: str) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS count FROM raw_messages WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    return int(row["count"])

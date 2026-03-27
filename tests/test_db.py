from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from telegram_group_summarizer.collection import placeholder_target
from telegram_group_summarizer.config import AppConfig
from telegram_group_summarizer.db import MIGRATION_VERSION, ensure_database, upsert_report_target
from telegram_group_summarizer.models import TargetReference


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.config = AppConfig(
            repo_root=root,
            db_path=root / "data" / "sqlite" / "test.db",
            reports_dir=root / "data" / "reports",
            sessions_dir=root / "data" / "sessions",
            logs_dir=root / "logs",
            telegram_api_id=None,
            telegram_api_hash=None,
            session_name="test-session",
            default_lookback_hours=24,
            max_lookback_hours=24,
            default_max_messages=500,
            sqlite_busy_timeout_ms=5000,
            log_level="INFO",
        )
        self.connection = ensure_database(self.config)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def test_schema_creation_enables_expected_tables_and_migration_record(self) -> None:
        tables = {
            row["name"]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        self.assertIn("report_targets", tables)
        self.assertIn("collection_runs", tables)
        self.assertIn("raw_messages", tables)
        self.assertIn("generated_reports", tables)

        migration = self.connection.execute("SELECT version FROM schema_migrations").fetchone()
        self.assertEqual(MIGRATION_VERSION, migration["version"])

        journal_mode = self.connection.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual("wal", str(journal_mode).lower())

    def test_report_target_key_is_unique(self) -> None:
        target = placeholder_target("team_alpha", TargetReference(kind="target_key", value="team_alpha"))
        upsert_report_target(self.connection, target)
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO report_targets(target_key, display_name, created_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
                """,
                ("team_alpha", "Duplicate"),
            )


if __name__ == "__main__":
    unittest.main()

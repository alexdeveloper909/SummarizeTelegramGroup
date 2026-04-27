from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram_group_summarizer.collection import collect_messages_for_run
from telegram_group_summarizer.config import AppConfig
from telegram_group_summarizer.consolidation import (
    build_consolidated_markdown,
    write_consolidated_outputs,
)
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.models import ResolvedTarget, TargetReference
from telegram_group_summarizer.reports import store_report


class FakeSender:
    def __init__(self, first_name: str, last_name: str) -> None:
        self.first_name = first_name
        self.last_name = last_name


class FakeMessage:
    def __init__(self, id: int, date: datetime, sender_id: int, sender, text: str) -> None:
        self.id = id
        self.date = date
        self.sender_id = sender_id
        self.sender = sender
        self.text = text
        self.unread = False


class FakeTelegramClient:
    def __init__(self, resolved_target: ResolvedTarget, lookback_messages=None):
        self.resolved_target = resolved_target
        self.lookback_messages = lookback_messages or []

    async def resolve_target(self, reference: TargetReference) -> ResolvedTarget:
        return self.resolved_target

    async def fetch_unread_messages(self, target: ResolvedTarget, limit: int):
        return []

    async def fetch_messages_since(self, target: ResolvedTarget, since: datetime, limit: int):
        return [message for message in self.lookback_messages if message.date >= since][:limit]


class ConsolidationTests(unittest.IsolatedAsyncioTestCase):
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
            max_lookback_hours=72,
            default_max_messages=500,
            sqlite_busy_timeout_ms=5000,
            log_level="INFO",
        )
        self.connection = ensure_database(self.config)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    async def test_consolidated_markdown_includes_reports_and_failures(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="group_one",
            entity_id=301,
            entity_type="channel",
            display_name="Group One",
            reference=TargetReference(kind="username", value="group_one"),
        )
        client = FakeTelegramClient(
            resolved_target,
            lookback_messages=[
                FakeMessage(
                    id=1,
                    date=now - timedelta(hours=1),
                    sender_id=1,
                    sender=FakeSender("Alice", "Smith"),
                    text="Important update",
                )
            ],
        )
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="group_one",
            lookback_hours=48,
            max_messages=10,
            config=self.config,
            run_id="run-group-one",
            now=now,
            collection_strategy="lookback-only",
        )
        empty_resolved_target = ResolvedTarget(
            target_key="empty_forum",
            entity_id=302,
            entity_type="channel",
            display_name="Empty Forum",
            reference=TargetReference(kind="username", value="empty_forum"),
        )
        empty_client = FakeTelegramClient(empty_resolved_target, lookback_messages=[])
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=empty_client,
            target_value="empty_forum",
            lookback_hours=48,
            max_messages=10,
            config=self.config,
            run_id="run-empty-forum",
            now=now,
            collection_strategy="lookback-only",
        )
        store_report(
            self.connection,
            run_id="run-group-one",
            report_markdown="# Headline summary\n\nGroup One did something important.",
            config=self.config,
        )
        store_report(
            self.connection,
            run_id="run-empty-forum",
            report_markdown="# Headline summary\n\nNo collected messages for this source.",
            config=self.config,
        )

        manifest = {
            "job_name": "Evening Digest",
            "started_at": now.isoformat(),
            "report_language": "Ukrainian",
            "delivery_target": "-100delivery",
            "lookback_hours": 48,
            "collection_strategy": "lookback-only",
            "prepared_target_count": 2,
            "failed_target_count": 1,
            "targets": [
                {
                    "status": "prepared",
                    "label": "Group One",
                    "target": "group_one",
                    "target_mode": "chat",
                    "run_id": "run-group-one",
                    "resolved_target_key": "group_one",
                    "resolved_display_name": "Group One",
                    "message_count": 1,
                },
                {
                    "status": "prepared",
                    "label": "Empty Forum",
                    "target": "empty_forum",
                    "target_mode": "forum",
                    "run_id": "run-empty-forum",
                    "resolved_target_key": "empty_forum",
                    "resolved_display_name": "Empty Forum",
                    "message_count": 0,
                },
                {
                    "status": "failed",
                    "label": "Broken Group",
                    "target": "broken_group",
                    "target_mode": "chat",
                    "error_summary": "Auth expired",
                },
            ],
        }

        markdown = build_consolidated_markdown(self.connection, manifest)
        outputs = write_consolidated_outputs(
            connection=self.connection,
            manifest=manifest,
            reports_dir=self.config.reports_dir,
        )

        self.assertIn("# Consolidated Telegram Digest", markdown)
        self.assertIn("## Group One", markdown)
        self.assertIn("Group One did something important.", markdown)
        self.assertIn("Empty Prepared Targets Skipped: 1", markdown)
        self.assertNotIn("## Empty Forum", markdown)
        self.assertNotIn("No collected messages for this source.", markdown)
        self.assertIn(
            "Broken Group: failed before report generation. Reason: Auth expired",
            markdown,
        )
        self.assertTrue(outputs["consolidated_report_path"].endswith(".md"))
        self.assertTrue(outputs["publish_prompt_path"].endswith(".report_prompt.md"))
        self.assertTrue(Path(outputs["consolidated_report_path"]).exists())
        self.assertTrue(Path(outputs["publish_prompt_path"]).exists())


if __name__ == "__main__":
    unittest.main()

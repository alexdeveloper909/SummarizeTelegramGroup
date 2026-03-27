from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram_group_summarizer.collection import collect_messages_for_run
from telegram_group_summarizer.config import AppConfig
from telegram_group_summarizer.db import count_raw_messages, ensure_database, get_run
from telegram_group_summarizer.finalization import finalize_run
from telegram_group_summarizer.models import ResolvedTarget, TargetReference
from telegram_group_summarizer.reports import store_report
from telegram_group_summarizer.summary_input import build_summary_bundle


@dataclass
class FakeSender:
    first_name: str
    last_name: str


@dataclass
class FakeMessage:
    id: int
    date: datetime
    sender_id: int
    sender: FakeSender
    text: str
    unread: bool = True


class FakeTelegramClient:
    def __init__(self, resolved_target: ResolvedTarget, unread_messages=None, lookback_messages=None):
        self.resolved_target = resolved_target
        self.unread_messages = unread_messages if unread_messages is not None else []
        self.lookback_messages = lookback_messages if lookback_messages is not None else []
        self.marked_read = []

    async def resolve_target(self, reference: TargetReference) -> ResolvedTarget:
        return self.resolved_target

    async def fetch_unread_messages(self, target: ResolvedTarget, limit: int):
        return list(self.unread_messages)[:limit]

    async def fetch_messages_since(self, target: ResolvedTarget, since: datetime, limit: int):
        return [message for message in self.lookback_messages if message.date >= since][:limit]

    async def mark_target_read(self, target: ResolvedTarget) -> None:
        self.marked_read.append(target.target_key)


class IntegrationFlowTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_mocked_pipeline_flow(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="team_alpha",
            entity_id=300,
            entity_type="channel",
            display_name="Team Alpha",
            reference=TargetReference(kind="username", value="team_alpha"),
        )
        lookback_messages = [
            FakeMessage(
                id=1,
                date=now - timedelta(minutes=10),
                sender_id=1,
                sender=FakeSender("Alice", "Smith"),
                text="Alpha update https://alpha.test",
                unread=False,
            ),
            FakeMessage(
                id=2,
                date=now - timedelta(minutes=5),
                sender_id=2,
                sender=FakeSender("Bob", "Jones"),
                text="Need follow-up",
                unread=False,
            ),
        ]
        client = FakeTelegramClient(resolved_target, unread_messages=[], lookback_messages=lookback_messages)

        collect_result = await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="team_alpha",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-integration",
            now=now,
        )
        bundle = build_summary_bundle(self.connection, "run-integration")
        self.assertEqual(2, len(bundle.messages))
        self.assertEqual("lookback", collect_result["mode"])

        store_report(
            self.connection,
            run_id="run-integration",
            report_markdown="# Headline summary\n\nA concise report.",
            config=self.config,
        )
        finalization_result = await finalize_run(
            connection=self.connection,
            telegram_client=client,
            run_id="run-integration",
            mark_read=True,
            purge_raw=True,
        )

        self.assertEqual(["team_alpha"], client.marked_read)
        self.assertEqual("finalized", get_run(self.connection, "run-integration")["status"])
        self.assertEqual(0, count_raw_messages(self.connection, "run-integration"))
        self.assertTrue(finalization_result["report_output_path"].endswith(".report.md"))


if __name__ == "__main__":
    unittest.main()

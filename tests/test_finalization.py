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


@dataclass
class FakeSender:
    first_name: str
    last_name: str


@dataclass
class FakeReply:
    reply_to_msg_id: int
    reply_to_top_id: int | None = None
    forum_topic: bool = False


@dataclass
class FakeMessage:
    id: int
    date: datetime
    sender_id: int
    sender: FakeSender
    text: str
    unread: bool = True
    reply_to: FakeReply | None = None


@dataclass
class FakeForumTopic:
    id: int
    title: str
    top_message: int
    date: datetime
    unread_count: int = 0
    unread_mentions_count: int = 0
    unread_reactions_count: int = 0
    pinned: bool = False
    closed: bool = False
    hidden: bool = False


class FakeTelegramClient:
    def __init__(self, resolved_target: ResolvedTarget, messages=None, forum_topics=None):
        self.resolved_target = resolved_target
        self.messages = messages if messages is not None else []
        self.forum_topics = forum_topics if forum_topics is not None else []
        self.marked_read = []
        self.marked_forum_topics = []

    async def resolve_target(self, reference: TargetReference) -> ResolvedTarget:
        return self.resolved_target

    async def fetch_unread_messages(self, target: ResolvedTarget, limit: int):
        return list(self.messages)[:limit]

    async def fetch_messages_since(self, target: ResolvedTarget, since: datetime, limit: int):
        return list(self.messages)[:limit]

    async def fetch_forum_topics(self, target: ResolvedTarget, limit=None):
        if limit is None:
            return list(self.forum_topics)
        return list(self.forum_topics)[:limit]

    async def fetch_forum_topic_messages(self, target: ResolvedTarget, topic, *, limit: int):
        topic_messages = [
            message
            for message in self.messages
            if message.reply_to is not None
            and message.reply_to.reply_to_top_id == topic.forum_topic_top_message_id
        ]
        return topic_messages[:limit]

    async def mark_target_read(self, target: ResolvedTarget) -> None:
        self.marked_read.append(target.target_key)

    async def mark_forum_topic_read(
        self,
        target: ResolvedTarget,
        *,
        topic_id: int,
        highest_message_id: int,
    ) -> None:
        self.marked_forum_topics.append((topic_id, highest_message_id))


class FinalizationTests(unittest.IsolatedAsyncioTestCase):
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
        self.now = datetime.now(timezone.utc)
        self.resolved_target = ResolvedTarget(
            target_key="team_alpha",
            entity_id=201,
            entity_type="channel",
            display_name="Team Alpha",
            reference=TargetReference(kind="username", value="team_alpha"),
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    async def _collect_run(self, run_id: str, messages=None) -> FakeTelegramClient:
        fake_client = FakeTelegramClient(
            self.resolved_target,
            messages=messages
            if messages is not None
            else [
                FakeMessage(
                    id=1,
                    date=self.now,
                    sender_id=1,
                    sender=FakeSender("Alice", "Smith"),
                    text="hello",
                )
            ],
        )
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=fake_client,
            target_value="team_alpha",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id=run_id,
            now=self.now,
        )
        return fake_client

    async def test_finalization_requires_report(self) -> None:
        fake_client = await self._collect_run("run-no-report")
        with self.assertRaises(ValueError):
            await finalize_run(
                connection=self.connection,
                telegram_client=fake_client,
                run_id="run-no-report",
                mark_read=True,
                purge_raw=True,
            )

    async def test_finalization_marks_read_and_purges_raw_messages(self) -> None:
        fake_client = await self._collect_run("run-finalize")
        store_report(
            self.connection,
            run_id="run-finalize",
            report_markdown="# Report\n\nDone.",
            config=self.config,
        )

        result = await finalize_run(
            connection=self.connection,
            telegram_client=fake_client,
            run_id="run-finalize",
            mark_read=True,
            purge_raw=True,
        )

        self.assertEqual(["team_alpha"], fake_client.marked_read)
        self.assertEqual(0, count_raw_messages(self.connection, "run-finalize"))
        self.assertEqual("finalized", get_run(self.connection, "run-finalize")["status"])
        self.assertGreaterEqual(result["purged_rows"], 1)
        self.assertEqual("chat", result["target_mode"])
        self.assertIn(f"/{self.now.strftime('%d.%m.%Y')}/report/", result["report_output_path"])

    async def test_forum_finalization_marks_only_collected_topics(self) -> None:
        resolved_target = ResolvedTarget(
            target_key="forum_room",
            entity_id=301,
            entity_type="channel",
            display_name="Forum Room",
            reference=TargetReference(kind="username", value="forum_room"),
            is_forum=True,
        )
        fake_client = FakeTelegramClient(
            resolved_target,
            messages=[
                FakeMessage(
                    id=101,
                    date=self.now - timedelta(minutes=20),
                    sender_id=1,
                    sender=FakeSender("Alice", "Smith"),
                    text="Launch thread",
                    reply_to=FakeReply(100, 100, True),
                ),
                FakeMessage(
                    id=102,
                    date=self.now - timedelta(minutes=10),
                    sender_id=2,
                    sender=FakeSender("Bob", "Jones"),
                    text="More launch thread",
                    reply_to=FakeReply(101, 100, True),
                ),
                FakeMessage(
                    id=201,
                    date=self.now - timedelta(minutes=5),
                    sender_id=3,
                    sender=FakeSender("Cara", "Lopez"),
                    text="Ops thread",
                    reply_to=FakeReply(200, 200, True),
                ),
            ],
            forum_topics=[
                FakeForumTopic(
                    id=10,
                    title="Launch",
                    top_message=100,
                    date=self.now,
                    unread_count=2,
                ),
                FakeForumTopic(
                    id=20,
                    title="Ops",
                    top_message=200,
                    date=self.now,
                    unread_count=1,
                ),
            ],
        )
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=fake_client,
            target_value="forum_room",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-forum-finalize",
            now=self.now,
            target_mode="forum",
        )
        store_report(
            self.connection,
            run_id="run-forum-finalize",
            report_markdown="# Report\n\nDone.",
            config=self.config,
        )

        result = await finalize_run(
            connection=self.connection,
            telegram_client=fake_client,
            run_id="run-forum-finalize",
            mark_read=True,
            purge_raw=True,
        )

        self.assertEqual([], fake_client.marked_read)
        self.assertEqual([(10, 102), (20, 201)], fake_client.marked_forum_topics)
        self.assertEqual("forum", result["target_mode"])
        self.assertEqual(0, count_raw_messages(self.connection, "run-forum-finalize"))

    async def test_finalization_is_retry_safe(self) -> None:
        fake_client = await self._collect_run("run-idempotent")
        store_report(
            self.connection,
            run_id="run-idempotent",
            report_markdown="# Report\n\nDone.",
            config=self.config,
        )

        await finalize_run(
            connection=self.connection,
            telegram_client=fake_client,
            run_id="run-idempotent",
            mark_read=True,
            purge_raw=True,
        )
        await finalize_run(
            connection=self.connection,
            telegram_client=fake_client,
            run_id="run-idempotent",
            mark_read=True,
            purge_raw=True,
        )

        self.assertEqual(["team_alpha"], fake_client.marked_read)
        self.assertEqual(0, count_raw_messages(self.connection, "run-idempotent"))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram_group_summarizer.collection import (
    collect_messages_for_run,
    derive_target_reference,
    normalize_message,
)
from telegram_group_summarizer.config import AppConfig
from telegram_group_summarizer.db import (
    ensure_database,
    get_run,
    get_target_by_key,
    list_raw_messages,
    list_run_forum_topics,
)
from telegram_group_summarizer.models import ResolvedTarget, TargetReference


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
class FakeForward:
    from_name: str


@dataclass
class FakeMessage:
    id: int
    date: datetime
    sender_id: int
    sender: FakeSender
    text: str
    reply_to: FakeReply | None = None
    fwd_from: FakeForward | None = None
    action: object | None = None
    media: object | None = None
    unread: bool = True


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
    def __init__(
        self,
        resolved_target: ResolvedTarget,
        unread_messages=None,
        lookback_messages=None,
        forum_topics=None,
        forum_messages_by_topic=None,
    ):
        self.resolved_target = resolved_target
        self.unread_messages = unread_messages if unread_messages is not None else []
        self.lookback_messages = lookback_messages if lookback_messages is not None else []
        self.forum_topics = forum_topics if forum_topics is not None else []
        self.forum_messages_by_topic = forum_messages_by_topic or {}
        self.marked_read = []

    async def resolve_target(self, reference: TargetReference) -> ResolvedTarget:
        return self.resolved_target

    async def fetch_unread_messages(self, target: ResolvedTarget, limit: int):
        return list(self.unread_messages)[:limit]

    async def fetch_messages_since(self, target: ResolvedTarget, since: datetime, limit: int):
        return [message for message in self.lookback_messages if message.date >= since][:limit]

    async def fetch_forum_topics(self, target: ResolvedTarget, limit=None):
        if limit is None:
            return list(self.forum_topics)
        return list(self.forum_topics)[:limit]

    async def fetch_forum_topic_messages(self, target: ResolvedTarget, topic, *, limit: int):
        return list(self.forum_messages_by_topic.get(topic.forum_topic_id, []))[:limit]

    async def mark_target_read(self, target: ResolvedTarget) -> None:
        self.marked_read.append(target.target_key)


class CollectionTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_normalize_message_extracts_links_replies_service_flags_and_forum_fields(
        self,
    ) -> None:
        now = datetime.now(timezone.utc)
        message = FakeMessage(
            id=100,
            date=now,
            sender_id=123,
            sender=FakeSender(first_name="Alice", last_name="Smith"),
            text="Check https://example.com now",
            reply_to=FakeReply(reply_to_msg_id=98, reply_to_top_id=77, forum_topic=True),
            fwd_from=FakeForward(from_name="Upstream"),
            action=object(),
            media=type("MessageMediaDocument", (), {})(),
        )

        normalized = normalize_message(
            run_id="run-1",
            target_id=7,
            message=message,
            forum_topic_id=55,
            forum_topic_top_message_id=77,
            is_forum_topic_message_value=True,
        )

        self.assertTrue(normalized.has_links)
        self.assertEqual(98, normalized.reply_to_message_id)
        self.assertEqual(77, normalized.reply_to_top_message_id)
        self.assertEqual(55, normalized.forum_topic_id)
        self.assertEqual(77, normalized.forum_topic_top_message_id)
        self.assertEqual("Upstream", normalized.forward_source)
        self.assertEqual("Alice Smith", normalized.sender_name)
        self.assertTrue(normalized.has_media)
        self.assertEqual("document", normalized.media_kind)
        self.assertTrue(normalized.is_service_message)
        self.assertTrue(normalized.is_forum_topic_message)

    async def test_collect_messages_prefers_unread_mode_and_records_run_status(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="team_alpha",
            entity_id=999,
            entity_type="channel",
            display_name="Team Alpha",
            reference=TargetReference(kind="username", value="team_alpha"),
        )
        unread_message = FakeMessage(
            id=1,
            date=now - timedelta(hours=1),
            sender_id=10,
            sender=FakeSender(first_name="Alice", last_name="Smith"),
            text="Unread update with https://example.com",
        )
        client = FakeTelegramClient(
            resolved_target, unread_messages=[unread_message], lookback_messages=[]
        )

        result = await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="team_alpha",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-collect-unread",
            now=now,
        )

        self.assertEqual("unread", result["mode"])
        self.assertEqual("chat", result["target_mode"])
        self.assertEqual(1, result["message_count"])
        run = get_run(self.connection, "run-collect-unread")
        self.assertEqual("collected", run["status"])
        self.assertEqual("unread", run["mode"])
        self.assertEqual("chat", run["target_mode"])
        self.assertEqual(1, run["message_count"])

        staged_rows = list_raw_messages(self.connection, "run-collect-unread")
        self.assertEqual(1, len(staged_rows))
        self.assertEqual("Unread update with https://example.com", staged_rows[0]["text_content"])
        self.assertEqual(0, staged_rows[0]["is_forum_topic_message"])

    async def test_collect_messages_can_force_lookback_only_mode(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="team_beta",
            entity_id=998,
            entity_type="channel",
            display_name="Team Beta",
            reference=TargetReference(kind="username", value="team_beta"),
        )
        unread_message = FakeMessage(
            id=1,
            date=now - timedelta(hours=1),
            sender_id=10,
            sender=FakeSender(first_name="Alice", last_name="Smith"),
            text="Unread update that should be ignored",
        )
        lookback_message = FakeMessage(
            id=2,
            date=now - timedelta(minutes=10),
            sender_id=11,
            sender=FakeSender(first_name="Bob", last_name="Jones"),
            text="Lookback update that should be kept",
            unread=False,
        )
        client = FakeTelegramClient(
            resolved_target,
            unread_messages=[unread_message],
            lookback_messages=[lookback_message],
        )

        result = await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="team_beta",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-collect-lookback-only",
            now=now,
            collection_strategy="lookback-only",
        )

        self.assertEqual("lookback", result["mode"])
        staged_rows = list_raw_messages(self.connection, "run-collect-lookback-only")
        self.assertEqual(1, len(staged_rows))
        self.assertEqual("Lookback update that should be kept", staged_rows[0]["text_content"])

    async def test_collect_messages_in_forum_mode_snapshots_and_stages_thread_metadata(
        self,
    ) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="product_forum",
            entity_id=1001,
            entity_type="channel",
            display_name="Product Forum",
            reference=TargetReference(kind="username", value="product_forum"),
            is_forum=True,
        )
        forum_topics = [
            FakeForumTopic(
                id=10,
                title="Launch",
                top_message=500,
                date=now - timedelta(hours=1),
                unread_count=4,
                pinned=True,
            ),
            FakeForumTopic(
                id=20,
                title="Minor Chatter",
                top_message=600,
                date=now - timedelta(days=2),
                unread_count=0,
            ),
        ]
        topic_messages = {
            10: [
                FakeMessage(
                    id=501,
                    date=now - timedelta(minutes=50),
                    sender_id=1,
                    sender=FakeSender("Alice", "Smith"),
                    text="Launch update https://launch.test",
                    reply_to=FakeReply(reply_to_msg_id=500, reply_to_top_id=500, forum_topic=True),
                ),
                FakeMessage(
                    id=502,
                    date=now - timedelta(minutes=20),
                    sender_id=2,
                    sender=FakeSender("Bob", "Jones"),
                    text="Need docs review",
                    reply_to=FakeReply(reply_to_msg_id=501, reply_to_top_id=500, forum_topic=True),
                ),
            ]
        }
        client = FakeTelegramClient(
            resolved_target,
            forum_topics=forum_topics,
            forum_messages_by_topic=topic_messages,
        )

        result = await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="product_forum",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-forum-collect",
            now=now,
            target_mode="forum",
            forum_topic_probe_messages=2,
            forum_max_messages_per_topic=5,
        )

        self.assertEqual("forum", result["mode"])
        self.assertEqual("forum", result["target_mode"])
        self.assertEqual(2, result["message_count"])
        self.assertEqual(2, result["forum_topic_count"])
        self.assertEqual(1, result["forum_active_topic_count"])

        run = get_run(self.connection, "run-forum-collect")
        self.assertEqual("forum", run["target_mode"])
        self.assertEqual(2, run["forum_topic_count"])
        self.assertEqual(1, run["forum_active_topic_count"])

        stored_topics = list_run_forum_topics(self.connection, "run-forum-collect")
        self.assertEqual(2, len(stored_topics))
        self.assertEqual("Launch", stored_topics[0]["forum_topic_title"])

        staged_rows = list_raw_messages(self.connection, "run-forum-collect")
        self.assertEqual(2, len(staged_rows))
        self.assertEqual(10, staged_rows[0]["forum_topic_id"])
        self.assertEqual(500, staged_rows[0]["forum_topic_top_message_id"])
        self.assertEqual(500, staged_rows[0]["reply_to_top_message_id"])
        self.assertEqual(1, staged_rows[0]["is_forum_topic_message"])

    async def test_target_parsing_prefers_existing_alias_then_username_and_numeric(self) -> None:
        self.connection.execute(
            """
            INSERT INTO report_targets(target_key, display_name, created_at, updated_at)
            VALUES ('team_alias', 'Team Alias', datetime('now'), datetime('now'))
            """
        )
        self.connection.commit()

        alias_reference = derive_target_reference(self.connection, "team_alias")
        username_reference = derive_target_reference(self.connection, "@teamusername")
        numeric_reference = derive_target_reference(self.connection, "-10012345")

        self.assertEqual(
            ("target_key", "team_alias"), (alias_reference.kind, alias_reference.value)
        )
        self.assertEqual(
            ("username", "teamusername"), (username_reference.kind, username_reference.value)
        )
        self.assertEqual(
            ("entity_id", "-10012345"), (numeric_reference.kind, numeric_reference.value)
        )
        self.assertIsNotNone(get_target_by_key(self.connection, "team_alias"))


if __name__ == "__main__":
    unittest.main()

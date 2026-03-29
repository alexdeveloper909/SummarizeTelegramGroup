from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram_group_summarizer.collection import collect_messages_for_run
from telegram_group_summarizer.config import AppConfig
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.models import ResolvedTarget, TargetReference
from telegram_group_summarizer.summary_input import (
    build_summary_bundle,
    bundle_to_json,
    bundle_to_markdown,
    write_summary_bundle,
)


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
    unread: bool = False
    reply_to: FakeReply | None = None
    action: object | None = None


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
        lookback_messages=None,
        forum_topics=None,
        forum_messages_by_topic=None,
    ):
        self.resolved_target = resolved_target
        self.lookback_messages = lookback_messages if lookback_messages is not None else []
        self.forum_topics = forum_topics if forum_topics is not None else []
        self.forum_messages_by_topic = forum_messages_by_topic or {}

    async def resolve_target(self, reference: TargetReference) -> ResolvedTarget:
        return self.resolved_target

    async def fetch_unread_messages(self, target: ResolvedTarget, limit: int):
        return []

    async def fetch_messages_since(self, target: ResolvedTarget, since: datetime, limit: int):
        return list(self.lookback_messages)[:limit]

    async def fetch_forum_topics(self, target: ResolvedTarget, limit=None):
        if limit is None:
            return list(self.forum_topics)
        return list(self.forum_topics)[:limit]

    async def fetch_forum_topic_messages(self, target: ResolvedTarget, topic, *, limit: int):
        return list(self.forum_messages_by_topic.get(topic.forum_topic_id, []))[:limit]


class SummaryInputTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_flat_bundle_generation_includes_sender_stats_urls_and_messages(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="team_alpha",
            entity_id=101,
            entity_type="channel",
            display_name="Team Alpha",
            reference=TargetReference(kind="username", value="team_alpha"),
        )
        messages = [
            FakeMessage(
                id=1,
                date=now,
                sender_id=1,
                sender=FakeSender("Alice", "Smith"),
                text="One https://a.test",
            ),
            FakeMessage(
                id=2,
                date=now,
                sender_id=2,
                sender=FakeSender("Bob", "Jones"),
                text="Two https://b.test",
            ),
        ]
        client = FakeTelegramClient(resolved_target, lookback_messages=messages)
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="team_alpha",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-summary",
            now=now,
        )

        bundle = build_summary_bundle(self.connection, "run-summary")
        bundle_json = bundle_to_json(bundle)
        markdown = bundle_to_markdown(bundle)

        self.assertEqual(2, len(bundle.messages))
        self.assertEqual(["https://a.test", "https://b.test"], bundle.candidate_urls)
        self.assertEqual("Alice Smith", bundle.sender_stats[0].sender_name)
        self.assertIn("candidate_urls", bundle_json)
        self.assertIn("sender_stats", bundle_json)
        self.assertIn("# Summary Input for Team Alpha", markdown)
        self.assertIn("## Target Metadata", markdown)
        self.assertIn("- Display Name: Team Alpha", markdown)
        self.assertIn("- Target Key: team_alpha", markdown)
        self.assertIn("- Entity Type: channel", markdown)
        self.assertIn("Full Chronological Messages", markdown)

    async def test_forum_bundle_uses_topic_radar_and_collapsed_activity(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="forum_room",
            entity_id=102,
            entity_type="channel",
            display_name="Forum Room",
            reference=TargetReference(kind="username", value="forum_room"),
            is_forum=True,
        )
        topics = [
            FakeForumTopic(
                id=10,
                title="Launch",
                top_message=100,
                date=now - timedelta(hours=1),
                unread_count=3,
                pinned=True,
            ),
            FakeForumTopic(
                id=20,
                title="Ops",
                top_message=200,
                date=now - timedelta(hours=2),
                unread_count=1,
            ),
            FakeForumTopic(
                id=30,
                title="Low Signal",
                top_message=300,
                date=now - timedelta(hours=3),
                unread_count=0,
            ),
            FakeForumTopic(
                id=40,
                title="Low Signal 2",
                top_message=400,
                date=now - timedelta(hours=4),
                unread_count=0,
            ),
            FakeForumTopic(
                id=50,
                title="Low Signal 3",
                top_message=500,
                date=now - timedelta(hours=5),
                unread_count=0,
            ),
            FakeForumTopic(
                id=60,
                title="Low Signal 4",
                top_message=600,
                date=now - timedelta(hours=6),
                unread_count=0,
            ),
        ]
        forum_messages = {
            10: [
                FakeMessage(
                    id=101,
                    date=now - timedelta(minutes=30),
                    sender_id=1,
                    sender=FakeSender("Alice", "Smith"),
                    text="Launch thread https://launch.test",
                    reply_to=FakeReply(100, 100, True),
                ),
                FakeMessage(
                    id=102,
                    date=now - timedelta(minutes=10),
                    sender_id=2,
                    sender=FakeSender("Bob", "Jones"),
                    text="Need release notes",
                    reply_to=FakeReply(101, 100, True),
                ),
            ],
            20: [
                FakeMessage(
                    id=201,
                    date=now - timedelta(minutes=45),
                    sender_id=3,
                    sender=FakeSender("Cara", "Lopez"),
                    text="Ops topic https://ops.test",
                    reply_to=FakeReply(200, 200, True),
                )
            ],
            30: [
                FakeMessage(
                    id=301,
                    date=now - timedelta(minutes=55),
                    sender_id=4,
                    sender=FakeSender("Dan", "Kim"),
                    text="tiny note",
                    reply_to=FakeReply(300, 300, True),
                )
            ],
            40: [
                FakeMessage(
                    id=401,
                    date=now - timedelta(minutes=65),
                    sender_id=5,
                    sender=FakeSender("Eve", "Stone"),
                    text="tiny note",
                    reply_to=FakeReply(400, 400, True),
                )
            ],
            50: [
                FakeMessage(
                    id=501,
                    date=now - timedelta(minutes=75),
                    sender_id=6,
                    sender=FakeSender("Finn", "Moore"),
                    text="tiny note",
                    reply_to=FakeReply(500, 500, True),
                )
            ],
            60: [
                FakeMessage(
                    id=601,
                    date=now - timedelta(minutes=85),
                    sender_id=7,
                    sender=FakeSender("Gail", "Parker"),
                    text="tiny note",
                    reply_to=FakeReply(600, 600, True),
                )
            ],
        }
        client = FakeTelegramClient(
            resolved_target,
            forum_topics=topics,
            forum_messages_by_topic=forum_messages,
        )
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="forum_room",
            lookback_hours=24,
            max_messages=20,
            config=self.config,
            run_id="run-forum-summary",
            now=now,
            target_mode="forum",
        )

        bundle = build_summary_bundle(self.connection, "run-forum-summary")
        markdown = bundle_to_markdown(bundle)
        bundle_json = bundle_to_json(bundle)

        self.assertTrue(bundle.target["is_forum"])
        self.assertIsNotNone(bundle.forum_overview)
        self.assertGreaterEqual(len(bundle.topic_index), 6)
        self.assertGreaterEqual(len(bundle.other_activity), 1)
        self.assertIn("Forum Overview", markdown)
        self.assertIn("Topic Radar", markdown)
        self.assertIn("Topic Excerpts", markdown)
        self.assertIn("Other Activity", markdown)
        self.assertIn("forum_overview", bundle_json)
        self.assertIn("topic_groups", bundle_json)

    async def test_forum_bundle_counts_distinct_sender_ids_when_names_are_missing(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="forum_room_missing_names",
            entity_id=105,
            entity_type="channel",
            display_name="Forum Missing Names",
            reference=TargetReference(kind="username", value="forum_room_missing_names"),
            is_forum=True,
        )
        topics = [
            FakeForumTopic(
                id=10,
                title="Tax Thread",
                top_message=100,
                date=now - timedelta(hours=1),
                unread_count=2,
            )
        ]
        forum_messages = {
            10: [
                FakeMessage(
                    id=101,
                    date=now - timedelta(minutes=30),
                    sender_id=1,
                    sender=FakeSender("", ""),
                    text="first",
                    reply_to=FakeReply(100, 100, True),
                ),
                FakeMessage(
                    id=102,
                    date=now - timedelta(minutes=20),
                    sender_id=2,
                    sender=FakeSender("", ""),
                    text="second",
                    reply_to=FakeReply(101, 100, True),
                ),
            ]
        }
        client = FakeTelegramClient(
            resolved_target,
            forum_topics=topics,
            forum_messages_by_topic=forum_messages,
        )
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="forum_room_missing_names",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-forum-missing-names",
            now=now,
            target_mode="forum",
        )

        bundle = build_summary_bundle(self.connection, "run-forum-missing-names")

        self.assertEqual(2, bundle.topic_index[0]["unique_sender_count"])
        self.assertEqual("sender:1", bundle.sender_stats[0].sender_name)
        self.assertEqual("sender:2", bundle.sender_stats[1].sender_name)

    async def test_empty_run_behavior_is_supported(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="quiet_room",
            entity_id=103,
            entity_type="channel",
            display_name="Quiet Room",
            reference=TargetReference(kind="username", value="quiet_room"),
        )
        client = FakeTelegramClient(resolved_target, lookback_messages=[])
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="quiet_room",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-empty",
            now=now,
        )

        bundle = build_summary_bundle(self.connection, "run-empty")
        markdown = bundle_to_markdown(bundle)

        self.assertEqual([], bundle.messages)
        self.assertEqual([], bundle.candidate_urls)
        self.assertIn("No messages staged for this run", markdown)

    async def test_write_summary_bundle_preserves_prefix_suffix_for_both_formats(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="prefix_room",
            entity_id=104,
            entity_type="channel",
            display_name="Prefix Room",
            reference=TargetReference(kind="username", value="prefix_room"),
        )
        client = FakeTelegramClient(
            resolved_target,
            lookback_messages=[
                FakeMessage(
                    id=1,
                    date=now,
                    sender_id=1,
                    sender=FakeSender("Alice", "Smith"),
                    text="Useful update",
                )
            ],
        )
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="prefix_room",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-prefix",
            now=now,
        )

        _, output_paths = write_summary_bundle(
            self.connection,
            run_id="run-prefix",
            output_format="both",
            output_path=self.config.reports_dir / "run-prefix.summary",
        )

        self.assertTrue(str(output_paths["json"]).endswith(".summary.json"))
        self.assertTrue(str(output_paths["markdown"]).endswith(".summary.md"))


if __name__ == "__main__":
    unittest.main()

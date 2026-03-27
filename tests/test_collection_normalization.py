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
from telegram_group_summarizer.db import ensure_database, get_run, get_target_by_key, list_raw_messages
from telegram_group_summarizer.models import ResolvedTarget, TargetReference


@dataclass
class FakeSender:
    first_name: str
    last_name: str


@dataclass
class FakeReply:
    reply_to_msg_id: int


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

    async def test_normalize_message_extracts_links_replies_and_service_flags(self) -> None:
        now = datetime.now(timezone.utc)
        message = FakeMessage(
            id=100,
            date=now,
            sender_id=123,
            sender=FakeSender(first_name="Alice", last_name="Smith"),
            text="Check https://example.com now",
            reply_to=FakeReply(reply_to_msg_id=98),
            fwd_from=FakeForward(from_name="Upstream"),
            action=object(),
            media=type("MessageMediaDocument", (), {})(),
        )

        normalized = normalize_message(run_id="run-1", target_id=7, message=message)

        self.assertTrue(normalized.has_links)
        self.assertEqual(98, normalized.reply_to_message_id)
        self.assertEqual("Upstream", normalized.forward_source)
        self.assertEqual("Alice Smith", normalized.sender_name)
        self.assertTrue(normalized.has_media)
        self.assertEqual("document", normalized.media_kind)
        self.assertTrue(normalized.is_service_message)

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
        client = FakeTelegramClient(resolved_target, unread_messages=[unread_message], lookback_messages=[])

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
        self.assertEqual(1, result["message_count"])
        run = get_run(self.connection, "run-collect-unread")
        self.assertEqual("collected", run["status"])
        self.assertEqual("unread", run["mode"])
        self.assertEqual(1, run["message_count"])

        staged_rows = list_raw_messages(self.connection, "run-collect-unread")
        self.assertEqual(1, len(staged_rows))
        self.assertEqual("Unread update with https://example.com", staged_rows[0]["text_content"])

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

        self.assertEqual(("target_key", "team_alias"), (alias_reference.kind, alias_reference.value))
        self.assertEqual(("username", "teamusername"), (username_reference.kind, username_reference.value))
        self.assertEqual(("entity_id", "-10012345"), (numeric_reference.kind, numeric_reference.value))
        self.assertIsNotNone(get_target_by_key(self.connection, "team_alias"))


if __name__ == "__main__":
    unittest.main()

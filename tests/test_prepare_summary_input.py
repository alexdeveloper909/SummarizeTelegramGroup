from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
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
class FakeMessage:
    id: int
    date: datetime
    sender_id: int
    sender: FakeSender
    text: str
    unread: bool = False


class FakeTelegramClient:
    def __init__(self, resolved_target: ResolvedTarget, lookback_messages=None):
        self.resolved_target = resolved_target
        self.lookback_messages = lookback_messages if lookback_messages is not None else []

    async def resolve_target(self, reference: TargetReference) -> ResolvedTarget:
        return self.resolved_target

    async def fetch_unread_messages(self, target: ResolvedTarget, limit: int):
        return []

    async def fetch_messages_since(self, target: ResolvedTarget, since: datetime, limit: int):
        return list(self.lookback_messages)[:limit]


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

    async def test_bundle_generation_includes_sender_stats_urls_and_chronological_messages(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="team_alpha",
            entity_id=101,
            entity_type="channel",
            display_name="Team Alpha",
            reference=TargetReference(kind="username", value="team_alpha"),
        )
        messages = [
            FakeMessage(id=1, date=now, sender_id=1, sender=FakeSender("Alice", "Smith"), text="One https://a.test"),
            FakeMessage(id=2, date=now, sender_id=2, sender=FakeSender("Bob", "Jones"), text="Two https://b.test"),
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
        self.assertIn("Full Chronological Messages", markdown)

    async def test_empty_run_behavior_is_supported(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="quiet_room",
            entity_id=102,
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
            entity_id=103,
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

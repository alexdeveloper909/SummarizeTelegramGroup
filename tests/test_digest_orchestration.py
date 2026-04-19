from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram_group_summarizer.config import AppConfig
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.digest_config import DigestRuntimeOptions, DigestTargetRuntimeOptions
from telegram_group_summarizer.digest_orchestration import collect_digest_context
from telegram_group_summarizer.models import ResolvedTarget, TargetReference


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
    def __init__(self, targets: dict[str, ResolvedTarget], messages: dict[str, list[FakeMessage]]):
        self.targets = targets
        self.messages = messages

    async def resolve_target(self, reference: TargetReference) -> ResolvedTarget:
        if reference.value not in self.targets:
            raise ValueError(f"Unknown target {reference.value}")
        return self.targets[reference.value]

    async def fetch_unread_messages(self, target: ResolvedTarget, limit: int):
        return []

    async def fetch_messages_since(self, target: ResolvedTarget, since: datetime, limit: int):
        return [
            message
            for message in self.messages.get(target.target_key, [])
            if message.date >= since
        ][:limit]


class DigestOrchestrationTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_collect_digest_context_keeps_partial_failures(self) -> None:
        now = datetime.now(timezone.utc)
        targets = {
            "good_group": ResolvedTarget(
                target_key="good_group",
                entity_id=201,
                entity_type="channel",
                display_name="Good Group",
                reference=TargetReference(kind="username", value="good_group"),
            )
        }
        messages = {
            "good_group": [
                FakeMessage(
                    id=1,
                    date=now - timedelta(hours=1),
                    sender_id=1,
                    sender=FakeSender("Alice", "Smith"),
                    text="Important update https://good.test",
                )
            ]
        }
        client = FakeTelegramClient(targets, messages)
        runtime = DigestRuntimeOptions(
            name="Evening Digest",
            report_language="Ukrainian",
            delivery_target="-100delivery",
            lookback_hours=48,
            max_messages=2000,
            collection_strategy="lookback-only",
            targets=[
                DigestTargetRuntimeOptions(
                    target="good_group",
                    label="Good Group",
                    target_mode="chat",
                    max_messages=2000,
                    forum_topic_limit=None,
                    forum_topic_probe_messages=None,
                    forum_max_messages_per_topic=None,
                ),
                DigestTargetRuntimeOptions(
                    target="missing_group",
                    label="Missing Group",
                    target_mode="chat",
                    max_messages=2000,
                    forum_topic_limit=None,
                    forum_topic_probe_messages=None,
                    forum_max_messages_per_topic=None,
                ),
            ],
        )

        manifest, manifest_path = await collect_digest_context(
            connection=self.connection,
            telegram_client=client,
            config=self.config,
            runtime_options=runtime,
            now=now,
        )

        self.assertTrue(manifest_path.exists())
        self.assertEqual(1, manifest["prepared_target_count"])
        self.assertEqual(1, manifest["failed_target_count"])
        prepared = [target for target in manifest["targets"] if target["status"] == "prepared"]
        failed = [target for target in manifest["targets"] if target["status"] == "failed"]
        self.assertEqual("Good Group", prepared[0]["label"])
        self.assertTrue(prepared[0]["summary_markdown_path"].endswith(".summary.md"))
        self.assertTrue(prepared[0]["report_prompt_path"].endswith(".report_prompt.md"))
        self.assertIn("Unknown target missing_group", failed[0]["error_summary"])


if __name__ == "__main__":
    unittest.main()

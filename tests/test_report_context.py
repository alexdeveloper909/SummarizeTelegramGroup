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
from telegram_group_summarizer.report_context import prepare_report_context


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
    reply_to_msg_id: int | None = None
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


class ReportContextTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_prepare_report_context_writes_bundle_and_prompt(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="team_alpha",
            entity_id=401,
            entity_type="channel",
            display_name="Team Alpha",
            reference=TargetReference(kind="username", value="team_alpha"),
        )
        client = FakeTelegramClient(
            resolved_target,
            lookback_messages=[
                FakeMessage(
                    id=1,
                    date=now,
                    sender_id=1,
                    sender=FakeSender("Alice", "Smith"),
                    text="Вкрали документи у парку",
                ),
                FakeMessage(
                    id=2,
                    date=now,
                    sender_id=2,
                    sender=FakeSender("Bob", "Jones"),
                    text="Контакт майстра +34685602628",
                ),
            ],
        )
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="team_alpha",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-report-context",
            now=now,
        )

        result = prepare_report_context(
            self.connection,
            run_id="run-report-context",
            config=self.config,
        )

        expected_date = now.strftime("%d.%m.%Y")
        self.assertEqual("run-report-context", result["run_id"])
        self.assertTrue(str(result["summary_json_path"]).endswith(".summary.json"))
        self.assertTrue(str(result["summary_markdown_path"]).endswith(".summary.md"))
        self.assertTrue(str(result["report_prompt_path"]).endswith(".report_prompt.md"))
        self.assertIn(f"/{expected_date}/summary/", str(result["summary_json_path"]))
        self.assertIn(f"/{expected_date}/summary/", str(result["summary_markdown_path"]))
        self.assertIn(f"/{expected_date}/report_prompt/", str(result["report_prompt_path"]))
        self.assertEqual(2, result["message_count"])
        self.assertTrue(Path(str(result["summary_json_path"])).exists())
        self.assertTrue(Path(str(result["summary_markdown_path"])).exists())
        self.assertTrue(Path(str(result["report_prompt_path"])).exists())
        prompt_text = Path(str(result["report_prompt_path"])).read_text(encoding="utf-8")
        self.assertIn("Source Target Display Name: Team Alpha", prompt_text)


if __name__ == "__main__":
    unittest.main()

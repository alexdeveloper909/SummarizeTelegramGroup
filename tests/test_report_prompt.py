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
from telegram_group_summarizer.report_prompt import build_report_prompt, write_report_prompt
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


class ReportPromptTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_report_prompt_prioritizes_compact_sections(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="team_alpha",
            entity_id=201,
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
                text="Important update https://docs.test",
            ),
            FakeMessage(
                id=2,
                date=now,
                sender_id=2,
                sender=FakeSender("Bob", "Jones"),
                text="Second update",
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
            run_id="run-report-prompt",
            now=now,
        )

        bundle = build_summary_bundle(self.connection, "run-report-prompt")
        prompt = build_report_prompt(bundle)

        self.assertIn("# Report Writing Brief", prompt)
        self.assertIn("## Reading Order", prompt)
        self.assertIn("1. Run Metadata", prompt)
        self.assertIn("2. Candidate URLs", prompt)
        self.assertIn("## Candidate URLs", prompt)
        self.assertIn("## Sender Statistics", prompt)
        self.assertIn("Start the report with one source line", prompt)
        self.assertIn("Source Target Display Name: Team Alpha", prompt)
        self.assertIn("Source Target Key: team_alpha", prompt)
        self.assertIn("## Final Reminder", prompt)
        self.assertNotIn("Low-confidence items or uncertainties", prompt)

    async def test_write_report_prompt_persists_output(self) -> None:
        now = datetime.now(timezone.utc)
        resolved_target = ResolvedTarget(
            target_key="quiet_room",
            entity_id=202,
            entity_type="channel",
            display_name="Quiet Room",
            reference=TargetReference(kind="username", value="quiet_room"),
        )
        client = FakeTelegramClient(
            resolved_target,
            lookback_messages=[
                FakeMessage(
                    id=1,
                    date=now,
                    sender_id=1,
                    sender=FakeSender("Alice", "Smith"),
                    text="Simple update",
                )
            ],
        )
        await collect_messages_for_run(
            connection=self.connection,
            telegram_client=client,
            target_value="quiet_room",
            lookback_hours=24,
            max_messages=10,
            config=self.config,
            run_id="run-report-prompt-write",
            now=now,
        )

        bundle = build_summary_bundle(self.connection, "run-report-prompt-write")
        output_path = write_report_prompt(
            bundle,
            output_path=None,
            reports_dir=self.config.reports_dir,
        )

        expected_date = now.strftime("%d.%m.%Y")
        self.assertEqual("report_prompt", output_path.parent.name)
        self.assertEqual(expected_date, output_path.parent.parent.name)
        self.assertTrue(output_path.name.endswith(".report_prompt.md"))
        self.assertTrue(output_path.exists())
        prompt_text = output_path.read_text(encoding="utf-8")
        self.assertIn("Report Writing Brief", prompt_text)
        self.assertIn("Do not omit the source target", prompt_text)


if __name__ == "__main__":
    unittest.main()

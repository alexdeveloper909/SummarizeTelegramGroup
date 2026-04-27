from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from telegram_group_summarizer.config import AppConfig
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.models import ResolvedTarget, TargetReference
from telegram_group_summarizer.report_delivery import (
    build_message_chunks,
    read_markdown_report,
    send_markdown_report,
)


@dataclass(frozen=True)
class FakeFormatterEntity:
    type: str
    offset: int
    length: int
    url: str | None = None
    language: str | None = None
    custom_emoji_id: str | None = None


class _FakeEntityBase:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class FakeTelethonTypes:
    class MessageEntityBold(_FakeEntityBase):
        pass

    class MessageEntityItalic(_FakeEntityBase):
        pass

    class MessageEntityUnderline(_FakeEntityBase):
        pass

    class MessageEntityStrike(_FakeEntityBase):
        pass

    class MessageEntitySpoiler(_FakeEntityBase):
        pass

    class MessageEntityCode(_FakeEntityBase):
        pass

    class MessageEntityPre(_FakeEntityBase):
        pass

    class MessageEntityTextUrl(_FakeEntityBase):
        pass

    class MessageEntityBlockquote(_FakeEntityBase):
        pass

    class MessageEntityCustomEmoji(_FakeEntityBase):
        pass


class FakeDeliveryClient:
    def __init__(self) -> None:
        self.references = []
        self.sent_messages = []

    async def resolve_target(self, reference: TargetReference) -> ResolvedTarget:
        self.references.append(reference)
        return ResolvedTarget(
            target_key=reference.value,
            entity_id=-1001234567890,
            entity_type="channel",
            display_name="Summary Reports",
            reference=reference,
        )

    async def send_text_message(
        self,
        target: ResolvedTarget,
        text: str,
        *,
        formatting_entities=None,
        link_preview: bool = False,
        topic_id: int | None = None,
    ):
        self.sent_messages.append(
            {
                "target": target,
                "text": text,
                "formatting_entities": tuple(formatting_entities or []),
                "link_preview": link_preview,
                "topic_id": topic_id,
            }
        )
        return SimpleNamespace(id=len(self.sent_messages))


class ReportDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.config = AppConfig(
            repo_root=root,
            db_path=root / "data" / "sqlite" / "test.db",
            reports_dir=root / "data" / "reports",
            sessions_dir=root / "data" / "sessions",
            logs_dir=root / "logs",
            telegram_api_id="12345",
            telegram_api_hash="hash",
            session_name="session",
            default_lookback_hours=24,
            max_lookback_hours=24,
            default_max_messages=500,
            sqlite_busy_timeout_ms=5000,
            log_level="INFO",
        )
        self.connection = ensure_database(self.config)

    def tearDown(self) -> None:
        self.connection.close()
        self.tempdir.cleanup()

    def test_read_markdown_report_rejects_empty_file(self) -> None:
        report_path = Path(self.tempdir.name) / "empty.md"
        report_path.write_text("  \n", encoding="utf-8")

        with self.assertRaises(ValueError):
            read_markdown_report(report_path)

    def test_build_message_chunks_maps_entities_and_uses_requested_limit(self) -> None:
        observed_limits = []

        def fake_convert(markdown_text: str):
            self.assertEqual("# Report", markdown_text)
            return (
                "Hello world",
                [
                    FakeFormatterEntity(type="bold", offset=0, length=5),
                    FakeFormatterEntity(
                        type="text_link",
                        offset=6,
                        length=5,
                        url="https://example.com",
                    ),
                ],
            )

        def fake_split(text: str, entities: list[object], max_message_length: int):
            observed_limits.append(max_message_length)
            self.assertEqual("Hello world", text)
            self.assertEqual(2, len(entities))
            return [
                ("Hello", [FakeFormatterEntity(type="bold", offset=0, length=5)]),
                (
                    "world",
                    [
                        FakeFormatterEntity(
                            type="text_link",
                            offset=0,
                            length=5,
                            url="https://example.com",
                        )
                    ],
                ),
            ]

        chunks = build_message_chunks(
            "# Report",
            max_message_length=32,
            formatter=(fake_convert, fake_split),
            telethon_types=FakeTelethonTypes,
        )

        self.assertEqual([32], observed_limits)
        self.assertEqual(["Hello", "world"], [chunk.text for chunk in chunks])
        self.assertEqual("MessageEntityBold", chunks[0].formatting_entities[0].__class__.__name__)
        self.assertEqual(
            "MessageEntityTextUrl", chunks[1].formatting_entities[0].__class__.__name__
        )
        self.assertEqual(
            "https://example.com",
            chunks[1].formatting_entities[0].url,
        )

    async def test_send_markdown_report_resolves_target_and_sends_all_chunks(self) -> None:
        fake_client = FakeDeliveryClient()

        def fake_convert(markdown_text: str):
            self.assertIn("summary", markdown_text)
            return (
                "Part one\nPart two",
                [FakeFormatterEntity(type="bold", offset=0, length=4)],
            )

        def fake_split(text: str, entities: list[object], max_message_length: int):
            self.assertEqual("Part one\nPart two", text)
            self.assertEqual(64, max_message_length)
            return [
                ("Part one", [FakeFormatterEntity(type="bold", offset=0, length=4)]),
                ("Part two", []),
            ]

        result = await send_markdown_report(
            connection=self.connection,
            telegram_client=fake_client,
            target_value="-1001234567890",
            markdown_text="summary body",
            topic_id=2,
            link_preview=True,
            max_message_length=64,
            formatter=(fake_convert, fake_split),
            telethon_types=FakeTelethonTypes,
        )

        self.assertEqual(1, len(fake_client.references))
        self.assertEqual("entity_id", fake_client.references[0].kind)
        self.assertEqual(2, len(fake_client.sent_messages))
        self.assertTrue(all(message["link_preview"] for message in fake_client.sent_messages))
        self.assertTrue(all(message["topic_id"] == 2 for message in fake_client.sent_messages))
        self.assertEqual(
            ["Part one", "Part two"], [message["text"] for message in fake_client.sent_messages]
        )
        self.assertEqual([1, 2], result["message_ids"])
        self.assertEqual(2, result["chunk_count"])
        self.assertEqual(2, result["topic_id"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from telegram_group_summarizer.models import ResolvedTarget, TargetReference
from telegram_group_summarizer.telethon_client import TelethonWorkflowClient


@dataclass
class FakeMessage:
    id: int
    date: datetime
    unread: bool = True


@dataclass
class FakeEntity:
    id: int
    title: str


class FakeTelethonClient:
    def __init__(self, messages=None) -> None:
        self.messages = messages if messages is not None else []
        self.get_entity_calls = []
        self.get_input_entity_calls = []
        self.iter_messages_calls = []
        self.read_ack_calls = []

    async def get_entity(self, value):
        self.get_entity_calls.append(value)
        return FakeEntity(id=1843781678, title="Numeric Group")

    async def get_input_entity(self, value):
        self.get_input_entity_calls.append(value)
        return f"input:{value}"

    async def iter_messages(self, entity, limit: int):
        self.iter_messages_calls.append((entity, limit))
        for message in self.messages[:limit]:
            yield message

    async def send_read_acknowledge(self, entity) -> None:
        self.read_ack_calls.append(entity)


class TelethonWorkflowClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_target_converts_numeric_entity_id_to_int(self) -> None:
        client = FakeTelethonClient()
        workflow_client = TelethonWorkflowClient(client)

        resolved = await workflow_client.resolve_target(
            TargetReference(kind="entity_id", value="-1001843781678")
        )

        self.assertEqual([-1001843781678], client.get_entity_calls)
        self.assertEqual("-1001843781678", resolved.target_key)
        self.assertEqual(1843781678, resolved.entity_id)

    async def test_numeric_target_key_uses_input_entity_for_fetch_and_mark_read(self) -> None:
        client = FakeTelethonClient(
            messages=[FakeMessage(id=1, date=datetime.now(timezone.utc), unread=True)]
        )
        workflow_client = TelethonWorkflowClient(client)
        target = ResolvedTarget(
            target_key="-1001843781678",
            entity_id=1843781678,
            entity_type="channel",
            display_name="Numeric Group",
            reference=TargetReference(kind="target_key", value="-1001843781678"),
        )

        messages = await workflow_client.fetch_unread_messages(target, limit=10)
        await workflow_client.mark_target_read(target)

        self.assertEqual([-1001843781678, -1001843781678], client.get_input_entity_calls)
        self.assertEqual([("input:-1001843781678", 10)], client.iter_messages_calls)
        self.assertEqual(["input:-1001843781678"], client.read_ack_calls)
        self.assertEqual(1, len(messages))


if __name__ == "__main__":
    unittest.main()

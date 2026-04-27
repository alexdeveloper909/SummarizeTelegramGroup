from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from telegram_group_summarizer.models import ForumTopicSnapshot, ResolvedTarget, TargetReference
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
    forum: bool = False


@dataclass
class FakeRequest:
    name: str
    kwargs: dict


class FakeTelethonFunctions:
    class messages:
        @staticmethod
        def GetForumTopicsRequest(**kwargs):
            return FakeRequest("GetForumTopicsRequest", kwargs)

        @staticmethod
        def GetRepliesRequest(**kwargs):
            return FakeRequest("GetRepliesRequest", kwargs)

        @staticmethod
        def ReadDiscussionRequest(**kwargs):
            return FakeRequest("ReadDiscussionRequest", kwargs)


class FakeTelethonClient:
    def __init__(self, messages=None, forum_topics=None, replies=None) -> None:
        self.messages = messages if messages is not None else []
        self.forum_topics = forum_topics if forum_topics is not None else []
        self.replies = replies if replies is not None else []
        self.get_entity_calls = []
        self.get_input_entity_calls = []
        self.iter_messages_calls = []
        self.read_ack_calls = []
        self.send_message_calls = []
        self.request_calls = []

    async def get_entity(self, value):
        self.get_entity_calls.append(value)
        if value == "forum-room":
            return FakeEntity(id=1843781678, title="Forum Room", forum=True)
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

    async def send_message(self, entity, **kwargs):
        self.send_message_calls.append((entity, kwargs))
        return {"id": 99}

    async def __call__(self, request):
        self.request_calls.append(request)
        if request.name == "GetForumTopicsRequest":
            return SimpleNamespace(topics=list(self.forum_topics))
        if request.name == "GetRepliesRequest":
            return SimpleNamespace(messages=list(self.replies))
        if request.name == "ReadDiscussionRequest":
            return SimpleNamespace(ok=True)
        raise AssertionError(f"Unexpected request {request.name}")


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
        self.assertFalse(resolved.is_forum)

    async def test_resolve_target_marks_forum_enabled_entities(self) -> None:
        client = FakeTelethonClient()
        workflow_client = TelethonWorkflowClient(client)

        resolved = await workflow_client.resolve_target(
            TargetReference(kind="username", value="forum-room")
        )

        self.assertEqual(["forum-room"], client.get_entity_calls)
        self.assertTrue(resolved.is_forum)
        self.assertEqual("Forum Room", resolved.display_name)

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

    async def test_forum_methods_use_discussion_requests(self) -> None:
        client = FakeTelethonClient(
            forum_topics=[
                SimpleNamespace(
                    id=10,
                    title="Launch",
                    top_message=100,
                    date=datetime.now(timezone.utc),
                )
            ],
            replies=[
                FakeMessage(id=101, date=datetime.now(timezone.utc), unread=True),
                FakeMessage(id=102, date=datetime.now(timezone.utc), unread=True),
            ],
        )
        workflow_client = TelethonWorkflowClient(client)
        target = ResolvedTarget(
            target_key="forum-room",
            entity_id=1843781678,
            entity_type="channel",
            display_name="Forum Room",
            reference=TargetReference(kind="username", value="forum-room"),
            is_forum=True,
        )
        topic = ForumTopicSnapshot(
            run_id="run-1",
            target_id=7,
            forum_topic_id=10,
            forum_topic_title="Launch",
            forum_topic_top_message_id=100,
            forum_topic_date=datetime.now(timezone.utc),
            unread_count=1,
            unread_mentions_count=0,
            unread_reactions_count=0,
            is_pinned=False,
            is_closed=False,
            is_hidden=False,
        )

        with patch(
            "telegram_group_summarizer.telethon_client._load_telethon_functions",
            return_value=FakeTelethonFunctions,
        ):
            topics = await workflow_client.fetch_forum_topics(target, limit=10)
            replies = await workflow_client.fetch_forum_topic_messages(target, topic, limit=5)
            await workflow_client.mark_forum_topic_read(
                target,
                topic_id=10,
                highest_message_id=102,
            )

        self.assertEqual(["forum-room"] * 3, client.get_input_entity_calls)
        self.assertEqual(1, len(topics))
        self.assertEqual([102, 101], [message.id for message in replies])
        self.assertEqual(
            ["GetForumTopicsRequest", "GetRepliesRequest", "ReadDiscussionRequest"],
            [request.name for request in client.request_calls],
        )
        self.assertEqual(102, client.request_calls[-1].kwargs["read_max_id"])
        self.assertEqual(10, client.request_calls[-1].kwargs["msg_id"])

    async def test_send_text_message_reuses_input_entity_lookup(self) -> None:
        client = FakeTelethonClient()
        workflow_client = TelethonWorkflowClient(client)
        target = ResolvedTarget(
            target_key="-1001843781678",
            entity_id=1843781678,
            entity_type="channel",
            display_name="Numeric Group",
            reference=TargetReference(kind="target_key", value="-1001843781678"),
        )

        await workflow_client.send_text_message(
            target,
            "Hello",
            formatting_entities=("bold",),
            link_preview=True,
        )

        self.assertEqual([-1001843781678], client.get_input_entity_calls)
        self.assertEqual(
            [
                (
                    "input:-1001843781678",
                    {
                        "message": "Hello",
                        "formatting_entities": ["bold"],
                        "link_preview": True,
                    },
                )
            ],
            client.send_message_calls,
        )

    async def test_send_text_message_uses_reply_to_for_topic_delivery(self) -> None:
        client = FakeTelethonClient()
        workflow_client = TelethonWorkflowClient(client)
        target = ResolvedTarget(
            target_key="-1001843781678",
            entity_id=1843781678,
            entity_type="channel",
            display_name="Numeric Group",
            reference=TargetReference(kind="target_key", value="-1001843781678"),
        )

        with patch(
            "telegram_group_summarizer.telethon_client._build_topic_reply_object",
            side_effect=lambda topic_id: ("reply", topic_id),
        ):
            await workflow_client.send_text_message(
                target,
                "Hello topic",
                topic_id=2,
            )

        self.assertEqual([-1001843781678], client.get_input_entity_calls)
        self.assertEqual(
            [
                (
                    "input:-1001843781678",
                    {
                        "message": "Hello topic",
                        "link_preview": False,
                        "reply_to": ("reply", 2),
                    },
                )
            ],
            client.send_message_calls,
        )


if __name__ == "__main__":
    unittest.main()

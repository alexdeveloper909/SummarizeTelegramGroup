from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from .collection import normalize_datetime
from .config import AppConfig
from .models import ForumTopicSnapshot, ResolvedTarget, TargetReference


def _missing_telethon_error(exc: ImportError) -> RuntimeError:
    error = RuntimeError(
        "Telethon is required for Telegram access. Install it with `pip install '.[telegram]'`."
    )
    error.__cause__ = exc
    return error


def _load_telethon_client():
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise _missing_telethon_error(exc)
    return TelegramClient


def _load_telethon_functions():
    try:
        from telethon import functions
    except ImportError as exc:
        raise _missing_telethon_error(exc)
    return functions


def create_telethon_client(config: AppConfig, session_name: Optional[str] = None):
    telegram_client = _load_telethon_client()
    resolved_session_name = session_name or config.session_name
    session_path = config.sessions_dir / resolved_session_name
    session_path.parent.mkdir(parents=True, exist_ok=True)
    return telegram_client(str(session_path), config.telegram_api_id, config.telegram_api_hash)


class TelethonWorkflowClient:
    def __init__(self, client) -> None:
        self.client = client

    def _lookup_value(self, value: str, kind: str) -> object:
        if kind == "entity_id":
            return int(value)
        if kind == "target_key" and value.lstrip("-").isdigit():
            return int(value)
        return value

    async def _input_entity(self, target: ResolvedTarget):
        lookup_value = self._lookup_value(target.reference.value, target.reference.kind)
        return await self.client.get_input_entity(lookup_value)

    async def resolve_target(self, reference: TargetReference) -> ResolvedTarget:
        lookup_value = self._lookup_value(reference.value, reference.kind)
        entity = await self.client.get_entity(lookup_value)
        display_name = (
            getattr(entity, "title", None) or getattr(entity, "first_name", None) or reference.value
        )
        entity_type = entity.__class__.__name__.lower()
        entity_id = getattr(entity, "id", None)
        target_key = reference.value
        return ResolvedTarget(
            target_key=target_key,
            entity_id=entity_id,
            entity_type=entity_type,
            display_name=display_name,
            reference=reference,
            is_forum=bool(getattr(entity, "forum", False)),
        )

    async def fetch_unread_messages(self, target: ResolvedTarget, limit: int):
        input_entity = await self._input_entity(target)
        messages: List[object] = []
        async for message in self.client.iter_messages(input_entity, limit=limit):
            if not getattr(message, "unread", False):
                break
            messages.append(message)
        messages.reverse()
        return messages

    async def fetch_messages_since(self, target: ResolvedTarget, since: datetime, limit: int):
        input_entity = await self._input_entity(target)
        messages: List[object] = []
        async for message in self.client.iter_messages(input_entity, limit=limit):
            message_date = normalize_datetime(getattr(message, "date", None))
            if message_date < since:
                break
            messages.append(message)
        messages.reverse()
        return messages

    async def fetch_forum_topics(self, target: ResolvedTarget, limit: Optional[int] = None):
        functions = _load_telethon_functions()
        input_entity = await self._input_entity(target)
        topics: List[object] = []
        offset_date = None
        offset_id = 0
        offset_topic = 0
        remaining = limit

        while remaining is None or remaining > 0:
            page_limit = min(100, remaining) if remaining is not None else 100
            response = await self.client(
                functions.messages.GetForumTopicsRequest(
                    peer=input_entity,
                    offset_date=offset_date,
                    offset_id=offset_id,
                    offset_topic=offset_topic,
                    limit=page_limit,
                    q=None,
                )
            )
            page_topics = list(getattr(response, "topics", []) or [])
            if not page_topics:
                break
            topics.extend(page_topics)
            if remaining is not None:
                remaining -= len(page_topics)
                if remaining <= 0:
                    break
            last_topic = page_topics[-1]
            offset_date = getattr(last_topic, "date", None)
            offset_id = int(getattr(last_topic, "top_message", 0) or 0)
            offset_topic = int(getattr(last_topic, "id", 0) or 0)
            if len(page_topics) < page_limit:
                break
        return topics

    async def fetch_forum_topic_messages(
        self,
        target: ResolvedTarget,
        topic: ForumTopicSnapshot,
        *,
        limit: int,
    ):
        functions = _load_telethon_functions()
        input_entity = await self._input_entity(target)
        response = await self.client(
            functions.messages.GetRepliesRequest(
                peer=input_entity,
                msg_id=topic.forum_topic_id,
                offset_id=0,
                offset_date=None,
                add_offset=0,
                limit=limit,
                max_id=0,
                min_id=0,
                hash=0,
            )
        )
        messages = list(getattr(response, "messages", []) or [])
        messages.reverse()
        return messages

    async def mark_target_read(self, target: ResolvedTarget) -> None:
        input_entity = await self._input_entity(target)
        await self.client.send_read_acknowledge(input_entity)

    async def mark_forum_topic_read(
        self,
        target: ResolvedTarget,
        *,
        topic_id: int,
        highest_message_id: int,
    ) -> None:
        functions = _load_telethon_functions()
        input_entity = await self._input_entity(target)
        await self.client(
            functions.messages.ReadDiscussionRequest(
                peer=input_entity,
                msg_id=topic_id,
                read_max_id=highest_message_id,
            )
        )

    async def send_text_message(
        self,
        target: ResolvedTarget,
        text: str,
        *,
        formatting_entities: Optional[Iterable[object]] = None,
        link_preview: bool = False,
    ):
        input_entity = await self._input_entity(target)
        kwargs = {
            "message": text,
            "link_preview": link_preview,
        }
        if formatting_entities is not None:
            kwargs["formatting_entities"] = list(formatting_entities)
        return await self.client.send_message(input_entity, **kwargs)

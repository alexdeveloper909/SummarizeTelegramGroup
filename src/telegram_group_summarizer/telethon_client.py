from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from .collection import normalize_datetime
from .config import AppConfig
from .models import ResolvedTarget, TargetReference


def create_telethon_client(config: AppConfig, session_name: Optional[str] = None):
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise RuntimeError(
            "Telethon is required for Telegram access. Install it with `pip install '.[telegram]'`."
        ) from exc

    resolved_session_name = session_name or config.session_name
    session_path = config.sessions_dir / resolved_session_name
    session_path.parent.mkdir(parents=True, exist_ok=True)
    return TelegramClient(str(session_path), config.telegram_api_id, config.telegram_api_hash)


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

    async def mark_target_read(self, target: ResolvedTarget) -> None:
        input_entity = await self._input_entity(target)
        await self.client.send_read_acknowledge(input_entity)

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

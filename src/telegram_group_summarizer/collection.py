from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .config import AppConfig
from .db import (
    count_raw_messages,
    create_collection_run,
    get_target_by_key,
    insert_raw_messages,
    update_run_status,
    upsert_report_target,
)
from .models import NormalizedMessage, ResolvedTarget, TargetReference


URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,}$")


def generate_run_id() -> str:
    return uuid4().hex


def normalize_datetime(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def extract_text(message: Any) -> str:
    for attr in ("raw_text", "text", "message", "caption"):
        value = getattr(message, attr, None)
        if value:
            return str(value)
    return ""


def sender_display_name(sender: Any) -> Optional[str]:
    if sender is None:
        return None
    for attr in ("title", "first_name", "username"):
        value = getattr(sender, attr, None)
        if value:
            if attr == "first_name":
                last_name = getattr(sender, "last_name", None)
                return " ".join(part for part in [value, last_name] if part)
            return str(value)
    return None


def reply_to_message_id(message: Any) -> Optional[int]:
    direct = getattr(message, "reply_to_msg_id", None)
    if direct is not None:
        return int(direct)
    reply_to = getattr(message, "reply_to", None)
    nested = getattr(reply_to, "reply_to_msg_id", None)
    return int(nested) if nested is not None else None


def forward_source(message: Any) -> Optional[str]:
    direct = getattr(message, "forward_source", None)
    if direct:
        return str(direct)
    forwarded = getattr(message, "fwd_from", None)
    if forwarded is None:
        return None
    for attr in ("from_name",):
        value = getattr(forwarded, attr, None)
        if value:
            return str(value)
    from_id = getattr(forwarded, "from_id", None)
    if from_id is not None:
        for attr in ("user_id", "channel_id", "chat_id"):
            value = getattr(from_id, attr, None)
            if value is not None:
                return f"{attr}:{value}"
        return str(from_id)
    return forwarded.__class__.__name__


def detect_media_kind(message: Any) -> Optional[str]:
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "document", None):
        return "document"
    media = getattr(message, "media", None)
    if media is None:
        return None
    media_class_name = media.__class__.__name__.lower()
    if media_class_name.startswith("messagemedia"):
        media_class_name = media_class_name.replace("messagemedia", "", 1)
    return media_class_name or "media"


def is_service_message(message: Any) -> bool:
    return bool(getattr(message, "action", None) or getattr(message, "is_service", False))


def raw_message_payload(message: Any) -> str:
    payload = {
        "id": getattr(message, "id", None),
        "date": normalize_datetime(getattr(message, "date", None)).isoformat(),
        "sender_id": getattr(message, "sender_id", None),
        "text": extract_text(message),
        "reply_to_message_id": reply_to_message_id(message),
        "forward_source": forward_source(message),
        "media_kind": detect_media_kind(message),
        "is_service_message": is_service_message(message),
    }
    return json.dumps(payload, sort_keys=True)


def normalize_message(*, run_id: str, target_id: int, message: Any) -> NormalizedMessage:
    text = extract_text(message)
    sender = getattr(message, "sender", None)
    sender_name = getattr(message, "sender_name", None) or getattr(message, "post_author", None) or sender_display_name(sender)
    media_kind = detect_media_kind(message)
    timestamp = normalize_datetime(getattr(message, "date", None))
    edited_at = getattr(message, "edit_date", None)

    return NormalizedMessage(
        run_id=run_id,
        target_id=target_id,
        telegram_message_id=int(getattr(message, "id")),
        message_timestamp=timestamp,
        sender_id=getattr(message, "sender_id", None),
        sender_name=sender_name,
        text_content=text,
        reply_to_message_id=reply_to_message_id(message),
        forward_source=forward_source(message),
        has_links=bool(URL_PATTERN.search(text)),
        has_media=media_kind is not None,
        media_kind=media_kind,
        edited_at=normalize_datetime(edited_at) if edited_at else None,
        is_service_message=is_service_message(message),
        raw_json=raw_message_payload(message),
    )


def derive_target_reference(connection, target_value: str) -> TargetReference:
    existing = get_target_by_key(connection, target_value)
    if existing is not None:
        return TargetReference(kind="target_key", value=target_value)

    normalized = target_value.strip()
    if normalized.lstrip("-").isdigit():
        return TargetReference(kind="entity_id", value=normalized)
    if normalized.startswith("@"):
        return TargetReference(kind="username", value=normalized[1:])
    if USERNAME_PATTERN.match(normalized):
        return TargetReference(kind="username", value=normalized)
    return TargetReference(kind="target_key", value=normalized)


def placeholder_target(target_value: str, reference: TargetReference) -> ResolvedTarget:
    entity_id = int(reference.value) if reference.kind == "entity_id" else None
    display_name = reference.value if reference.kind != "target_key" else target_value
    target_key = target_value if reference.kind == "target_key" else reference.value
    return ResolvedTarget(
        target_key=target_key,
        entity_id=entity_id,
        entity_type=None,
        display_name=display_name,
        reference=reference,
    )


def _filter_by_cutoff(messages: List[Any], cutoff: datetime) -> List[Any]:
    filtered = []
    for message in messages:
        if normalize_datetime(getattr(message, "date", None)) >= cutoff:
            filtered.append(message)
    return filtered


async def collect_messages_for_run(
    *,
    connection,
    telegram_client,
    target_value: str,
    lookback_hours: int,
    max_messages: int,
    config: AppConfig,
    run_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    active_run_id = run_id or generate_run_id()
    effective_lookback_hours = min(lookback_hours, config.max_lookback_hours)
    effective_now = normalize_datetime(now)
    cutoff = effective_now - timedelta(hours=effective_lookback_hours)

    reference = derive_target_reference(connection, target_value)
    provisional_target = placeholder_target(target_value, reference)
    target_id = upsert_report_target(connection, provisional_target)
    create_collection_run(
        connection,
        run_id=active_run_id,
        target_id=target_id,
        lookback_hours=effective_lookback_hours,
    )

    try:
        resolved_target = await telegram_client.resolve_target(reference)
        target_id = upsert_report_target(connection, resolved_target)

        unread_messages = await telegram_client.fetch_unread_messages(resolved_target, limit=max_messages)
        collected_messages: List[Any] = []
        mode = "lookback"

        if unread_messages is not None:
            bounded_unread = _filter_by_cutoff(list(unread_messages), cutoff)
            if bounded_unread:
                collected_messages = bounded_unread[:max_messages]
                mode = "unread"

        if not collected_messages:
            lookback_messages = await telegram_client.fetch_messages_since(
                resolved_target,
                since=cutoff,
                limit=max_messages,
            )
            collected_messages = _filter_by_cutoff(list(lookback_messages), cutoff)[:max_messages]
            mode = "lookback"

        normalized_messages = [
            normalize_message(run_id=active_run_id, target_id=target_id, message=message)
            for message in collected_messages
        ]
        insert_raw_messages(connection, normalized_messages)
        persisted_count = count_raw_messages(connection, active_run_id)
        update_run_status(
            connection,
            active_run_id,
            status="collected",
            mode=mode,
            message_count=persisted_count,
            resolved_target=resolved_target,
        )
        return {
            "run_id": active_run_id,
            "target_id": target_id,
            "target_key": resolved_target.target_key,
            "mode": mode,
            "message_count": persisted_count,
            "lookback_hours": effective_lookback_hours,
        }
    except Exception as exc:
        update_run_status(
            connection,
            active_run_id,
            status="failed",
            error_summary=str(exc),
            completed=True,
        )
        raise

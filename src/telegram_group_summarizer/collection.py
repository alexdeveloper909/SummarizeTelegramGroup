from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from .config import AppConfig
from .db import (
    count_raw_messages,
    create_collection_run,
    get_target_by_key,
    insert_raw_messages,
    insert_run_forum_topics,
    update_run_status,
    upsert_report_target,
)
from .models import ForumTopicSnapshot, NormalizedMessage, ResolvedTarget, TargetReference

URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,}$")
DEFAULT_FORUM_TOPIC_PROBE_MESSAGES = 3
DEFAULT_FORUM_MAX_MESSAGES_PER_TOPIC = 50
VALID_TARGET_MODES = {"auto", "chat", "forum"}


@dataclass(frozen=True)
class ForumCollectionOptions:
    topic_limit: Optional[int] = None
    topic_probe_messages: int = DEFAULT_FORUM_TOPIC_PROBE_MESSAGES
    max_messages_per_topic: int = DEFAULT_FORUM_MAX_MESSAGES_PER_TOPIC


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


def reply_to_top_message_id(message: Any) -> Optional[int]:
    direct = getattr(message, "reply_to_top_id", None)
    if direct is not None:
        return int(direct)
    reply_to = getattr(message, "reply_to", None)
    nested = getattr(reply_to, "reply_to_top_id", None)
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


def is_forum_topic_message(message: Any, explicit_value: bool = False) -> bool:
    if explicit_value:
        return True
    if reply_to_top_message_id(message) is not None:
        return True
    reply_to = getattr(message, "reply_to", None)
    return bool(getattr(reply_to, "forum_topic", False))


def raw_message_payload(
    message: Any,
    *,
    forum_topic_id: Optional[int],
    forum_topic_top_message_id: Optional[int],
    is_forum_topic_message_value: bool,
) -> str:
    payload = {
        "id": getattr(message, "id", None),
        "date": normalize_datetime(getattr(message, "date", None)).isoformat(),
        "sender_id": getattr(message, "sender_id", None),
        "text": extract_text(message),
        "reply_to_message_id": reply_to_message_id(message),
        "reply_to_top_message_id": reply_to_top_message_id(message),
        "forward_source": forward_source(message),
        "media_kind": detect_media_kind(message),
        "is_service_message": is_service_message(message),
        "forum_topic_id": forum_topic_id,
        "forum_topic_top_message_id": forum_topic_top_message_id,
        "is_forum_topic_message": is_forum_topic_message_value,
    }
    return json.dumps(payload, sort_keys=True)


def normalize_message(
    *,
    run_id: str,
    target_id: int,
    message: Any,
    forum_topic_id: Optional[int] = None,
    forum_topic_top_message_id: Optional[int] = None,
    is_forum_topic_message_value: bool = False,
) -> NormalizedMessage:
    text = extract_text(message)
    sender = getattr(message, "sender", None)
    sender_name = (
        getattr(message, "sender_name", None)
        or getattr(message, "post_author", None)
        or sender_display_name(sender)
    )
    media_kind = detect_media_kind(message)
    timestamp = normalize_datetime(getattr(message, "date", None))
    edited_at = getattr(message, "edit_date", None)
    normalized_reply_to_top = reply_to_top_message_id(message)
    normalized_is_forum_topic_message = is_forum_topic_message(
        message, explicit_value=is_forum_topic_message_value
    )

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
        forum_topic_id=forum_topic_id,
        forum_topic_top_message_id=forum_topic_top_message_id or normalized_reply_to_top,
        reply_to_top_message_id=normalized_reply_to_top,
        is_forum_topic_message=normalized_is_forum_topic_message,
        raw_json=raw_message_payload(
            message,
            forum_topic_id=forum_topic_id,
            forum_topic_top_message_id=forum_topic_top_message_id or normalized_reply_to_top,
            is_forum_topic_message_value=normalized_is_forum_topic_message,
        ),
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


def normalize_forum_topic_snapshot(
    *, run_id: str, target_id: int, topic: Any
) -> ForumTopicSnapshot:
    title = getattr(topic, "title", None) or f"Topic {getattr(topic, 'id')}"
    return ForumTopicSnapshot(
        run_id=run_id,
        target_id=target_id,
        forum_topic_id=int(getattr(topic, "id")),
        forum_topic_title=str(title),
        forum_topic_top_message_id=int(getattr(topic, "top_message")),
        forum_topic_date=normalize_datetime(getattr(topic, "date", None)),
        unread_count=int(getattr(topic, "unread_count", 0) or 0),
        unread_mentions_count=int(getattr(topic, "unread_mentions_count", 0) or 0),
        unread_reactions_count=int(getattr(topic, "unread_reactions_count", 0) or 0),
        is_pinned=bool(getattr(topic, "pinned", False)),
        is_closed=bool(getattr(topic, "closed", False)),
        is_hidden=bool(getattr(topic, "hidden", False)),
    )


def is_active_forum_topic(topic: ForumTopicSnapshot, cutoff: datetime) -> bool:
    return topic.forum_topic_date >= cutoff or topic.unread_count > 0


def _filter_by_cutoff(messages: Sequence[Any], cutoff: datetime) -> List[Any]:
    filtered = []
    for message in messages:
        if normalize_datetime(getattr(message, "date", None)) >= cutoff:
            filtered.append(message)
    return filtered


def _dedupe_messages(messages: Sequence[Any]) -> List[Any]:
    unique_messages = {int(getattr(message, "id")): message for message in messages}
    return sorted(
        unique_messages.values(),
        key=lambda message: (
            normalize_datetime(getattr(message, "date", None)),
            int(getattr(message, "id")),
        ),
    )


def _slice_recent_messages(messages: Sequence[Any], *, cutoff: datetime, limit: int) -> List[Any]:
    if limit <= 0:
        return []
    filtered = _filter_by_cutoff(list(messages), cutoff)
    deduped = _dedupe_messages(filtered)
    return deduped[-limit:]


def _forum_topic_priority(topic: ForumTopicSnapshot, probe_message_count: int = 0) -> tuple:
    return (
        topic.unread_count,
        int(topic.is_pinned),
        probe_message_count,
        topic.unread_mentions_count,
        topic.unread_reactions_count,
        topic.forum_topic_date,
    )


def _resolve_target_mode(requested_target_mode: str, resolved_target: ResolvedTarget) -> str:
    if requested_target_mode not in VALID_TARGET_MODES:
        raise ValueError(f"target_mode must be one of {sorted(VALID_TARGET_MODES)}")
    if requested_target_mode == "chat":
        return "chat"
    if requested_target_mode == "forum":
        if not resolved_target.is_forum:
            raise ValueError(
                "Target "
                f"{resolved_target.display_name} is not forum-enabled, "
                "but forum mode was requested."
            )
        return "forum"
    return "forum" if resolved_target.is_forum else "chat"


async def _collect_flat_target_messages(
    *,
    telegram_client,
    resolved_target: ResolvedTarget,
    cutoff: datetime,
    max_messages: int,
) -> tuple[str, List[Any]]:
    unread_messages = await telegram_client.fetch_unread_messages(
        resolved_target, limit=max_messages
    )
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
    return mode, collected_messages


async def _collect_forum_target_messages(
    *,
    connection,
    telegram_client,
    resolved_target: ResolvedTarget,
    run_id: str,
    target_id: int,
    cutoff: datetime,
    max_messages: int,
    forum_options: ForumCollectionOptions,
) -> tuple[List[ForumTopicSnapshot], List[ForumTopicSnapshot], List[NormalizedMessage]]:
    raw_topics = await telegram_client.fetch_forum_topics(
        resolved_target, limit=forum_options.topic_limit
    )
    topic_snapshots = [
        normalize_forum_topic_snapshot(run_id=run_id, target_id=target_id, topic=topic)
        for topic in raw_topics
    ]
    insert_run_forum_topics(connection, topic_snapshots)

    active_topics = [topic for topic in topic_snapshots if is_active_forum_topic(topic, cutoff)]
    ranked_topics = sorted(active_topics, key=_forum_topic_priority, reverse=True)
    collected_by_topic: Dict[int, List[Any]] = {}
    remaining_budget = max_messages
    probe_limit = min(
        forum_options.topic_probe_messages,
        forum_options.max_messages_per_topic,
        max_messages,
    )

    for topic in ranked_topics:
        if remaining_budget <= 0:
            break
        current_limit = min(probe_limit, remaining_budget)
        if current_limit <= 0:
            break
        topic_messages = await telegram_client.fetch_forum_topic_messages(
            resolved_target,
            topic,
            limit=current_limit,
        )
        collected_by_topic[topic.forum_topic_id] = _slice_recent_messages(
            topic_messages,
            cutoff=cutoff,
            limit=current_limit,
        )
        remaining_budget -= len(collected_by_topic[topic.forum_topic_id])

    if remaining_budget > 0:
        reranked_topics = sorted(
            ranked_topics,
            key=lambda topic: _forum_topic_priority(
                topic,
                probe_message_count=len(collected_by_topic.get(topic.forum_topic_id, [])),
            ),
            reverse=True,
        )
        for topic in reranked_topics:
            if remaining_budget <= 0:
                break
            existing_messages = collected_by_topic.get(topic.forum_topic_id, [])
            desired_total = min(
                forum_options.max_messages_per_topic,
                len(existing_messages) + remaining_budget,
            )
            if desired_total <= len(existing_messages):
                continue
            topic_messages = await telegram_client.fetch_forum_topic_messages(
                resolved_target,
                topic,
                limit=desired_total,
            )
            merged_messages = _slice_recent_messages(
                [*existing_messages, *topic_messages],
                cutoff=cutoff,
                limit=desired_total,
            )
            additional_messages = len(merged_messages) - len(existing_messages)
            if additional_messages <= 0:
                continue
            collected_by_topic[topic.forum_topic_id] = merged_messages
            remaining_budget -= additional_messages

    normalized_messages: List[NormalizedMessage] = []
    for topic in ranked_topics:
        for message in collected_by_topic.get(topic.forum_topic_id, []):
            normalized_messages.append(
                normalize_message(
                    run_id=run_id,
                    target_id=target_id,
                    message=message,
                    forum_topic_id=topic.forum_topic_id,
                    forum_topic_top_message_id=topic.forum_topic_top_message_id,
                    is_forum_topic_message_value=True,
                )
            )
    normalized_messages.sort(
        key=lambda message: (message.message_timestamp, message.telegram_message_id)
    )
    return topic_snapshots, active_topics, normalized_messages


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
    target_mode: str = "auto",
    forum_topic_limit: Optional[int] = None,
    forum_topic_probe_messages: int = DEFAULT_FORUM_TOPIC_PROBE_MESSAGES,
    forum_max_messages_per_topic: int = DEFAULT_FORUM_MAX_MESSAGES_PER_TOPIC,
) -> Dict[str, Any]:
    active_run_id = run_id or generate_run_id()
    effective_lookback_hours = min(lookback_hours, config.max_lookback_hours)
    effective_now = normalize_datetime(now)
    cutoff = effective_now - timedelta(hours=effective_lookback_hours)

    if forum_topic_probe_messages <= 0:
        raise ValueError("forum_topic_probe_messages must be positive.")
    if forum_max_messages_per_topic <= 0:
        raise ValueError("forum_max_messages_per_topic must be positive.")

    forum_options = ForumCollectionOptions(
        topic_limit=forum_topic_limit,
        topic_probe_messages=forum_topic_probe_messages,
        max_messages_per_topic=forum_max_messages_per_topic,
    )

    reference = derive_target_reference(connection, target_value)
    provisional_target = placeholder_target(target_value, reference)
    target_id = upsert_report_target(connection, provisional_target)
    create_collection_run(
        connection,
        run_id=active_run_id,
        target_id=target_id,
        lookback_hours=effective_lookback_hours,
        target_mode=target_mode,
    )

    try:
        resolved_target = await telegram_client.resolve_target(reference)
        target_id = upsert_report_target(connection, resolved_target)
        effective_target_mode = _resolve_target_mode(target_mode, resolved_target)

        forum_topic_count = 0
        forum_active_topic_count = 0
        if effective_target_mode == "forum":
            (
                topic_snapshots,
                active_topics,
                normalized_messages,
            ) = await _collect_forum_target_messages(
                connection=connection,
                telegram_client=telegram_client,
                resolved_target=resolved_target,
                run_id=active_run_id,
                target_id=target_id,
                cutoff=cutoff,
                max_messages=max_messages,
                forum_options=forum_options,
            )
            mode = "forum"
            forum_topic_count = len(topic_snapshots)
            forum_active_topic_count = len(active_topics)
        else:
            mode, collected_messages = await _collect_flat_target_messages(
                telegram_client=telegram_client,
                resolved_target=resolved_target,
                cutoff=cutoff,
                max_messages=max_messages,
            )
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
            target_mode=effective_target_mode,
            message_count=persisted_count,
            forum_topic_count=forum_topic_count,
            forum_active_topic_count=forum_active_topic_count,
            resolved_target=resolved_target,
        )
        return {
            "run_id": active_run_id,
            "target_id": target_id,
            "target_key": resolved_target.target_key,
            "mode": mode,
            "target_mode": effective_target_mode,
            "message_count": persisted_count,
            "lookback_hours": effective_lookback_hours,
            "forum_topic_count": forum_topic_count,
            "forum_active_topic_count": forum_active_topic_count,
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

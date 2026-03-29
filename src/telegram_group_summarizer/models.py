from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class TargetReference:
    kind: str
    value: str


@dataclass(frozen=True)
class ResolvedTarget:
    target_key: str
    entity_id: Optional[int]
    entity_type: Optional[str]
    display_name: str
    reference: TargetReference
    is_forum: bool = False


@dataclass(frozen=True)
class NormalizedMessage:
    run_id: str
    target_id: int
    telegram_message_id: int
    message_timestamp: datetime
    sender_id: Optional[int]
    sender_name: Optional[str]
    text_content: str
    reply_to_message_id: Optional[int]
    forward_source: Optional[str]
    has_links: bool
    has_media: bool
    media_kind: Optional[str]
    edited_at: Optional[datetime]
    is_service_message: bool
    forum_topic_id: Optional[int]
    forum_topic_top_message_id: Optional[int]
    reply_to_top_message_id: Optional[int]
    is_forum_topic_message: bool
    raw_json: Optional[str]


@dataclass(frozen=True)
class SenderStat:
    sender_name: str
    message_count: int


@dataclass(frozen=True)
class ForumTopicSnapshot:
    run_id: str
    target_id: int
    forum_topic_id: int
    forum_topic_title: str
    forum_topic_top_message_id: int
    forum_topic_date: datetime
    unread_count: int
    unread_mentions_count: int
    unread_reactions_count: int
    is_pinned: bool
    is_closed: bool
    is_hidden: bool


@dataclass(frozen=True)
class SummaryBundle:
    run: Dict[str, Any]
    target: Dict[str, Any]
    messages: List[Dict[str, Any]]
    candidate_urls: List[str]
    sender_stats: List[SenderStat]
    reply_threads: Dict[str, List[int]] = field(default_factory=dict)
    forum_overview: Optional[Dict[str, Any]] = None
    topic_index: List[Dict[str, Any]] = field(default_factory=list)
    topic_groups: List[Dict[str, Any]] = field(default_factory=list)
    other_activity: List[Dict[str, Any]] = field(default_factory=list)

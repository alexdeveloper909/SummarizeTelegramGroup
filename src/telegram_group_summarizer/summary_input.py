from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .collection import URL_PATTERN, normalize_datetime
from .db import get_run_with_target, list_raw_messages, list_run_forum_topics
from .models import SenderStat, SummaryBundle


def _derived_output_path(output_path: Path, extension: str) -> Path:
    if output_path.suffix:
        return output_path.with_name(f"{output_path.name}{extension}")
    return output_path.with_suffix(extension)


def _run_started_at(run) -> datetime:
    return normalize_datetime(datetime.fromisoformat(str(run["started_at"])))


def _raw_row_to_message(row) -> Dict[str, object]:
    return {
        "telegram_message_id": row["telegram_message_id"],
        "message_timestamp": row["message_timestamp"],
        "sender_id": row["sender_id"],
        "sender_name": row["sender_name"],
        "text_content": row["text_content"],
        "reply_to_message_id": row["reply_to_message_id"],
        "forward_source": row["forward_source"],
        "has_links": bool(row["has_links"]),
        "has_media": bool(row["has_media"]),
        "media_kind": row["media_kind"],
        "edited_at": row["edited_at"],
        "is_service_message": bool(row["is_service_message"]),
        "forum_topic_id": row["forum_topic_id"],
        "forum_topic_top_message_id": row["forum_topic_top_message_id"],
        "reply_to_top_message_id": row["reply_to_top_message_id"],
        "is_forum_topic_message": bool(row["is_forum_topic_message"]),
    }


def _base_bundle_parts(raw_messages) -> tuple[
    List[Dict[str, object]],
    List[str],
    List[SenderStat],
    Dict[str, List[int]],
]:
    messages: List[Dict[str, object]] = []
    candidate_urls: List[str] = []
    seen_urls = set()
    sender_counter: Counter[str] = Counter()
    reply_threads = defaultdict(list)

    for row in raw_messages:
        message = _raw_row_to_message(row)
        messages.append(message)

        sender_name = row["sender_name"] or "Unknown"
        sender_counter[sender_name] += 1
        if row["reply_to_message_id"] is not None:
            reply_threads[str(row["reply_to_message_id"])].append(int(row["telegram_message_id"]))

        for match in URL_PATTERN.findall(row["text_content"]):
            if match not in seen_urls:
                seen_urls.add(match)
                candidate_urls.append(match)

    sender_stats = [
        SenderStat(sender_name=name, message_count=count)
        for name, count in sender_counter.most_common()
    ]
    return messages, candidate_urls, sender_stats, dict(reply_threads)


def _is_active_forum_topic(topic_row, grouped_messages, cutoff: datetime) -> bool:
    topic_id = int(topic_row["forum_topic_id"])
    topic_date = normalize_datetime(datetime.fromisoformat(str(topic_row["forum_topic_date"])))
    return (
        topic_date >= cutoff
        or int(topic_row["unread_count"]) > 0
        or topic_id in grouped_messages
    )


def _forum_topic_priority(topic_entry: Dict[str, object]) -> tuple:
    return (
        int(topic_entry["unread_count"]),
        int(bool(topic_entry["is_pinned"])),
        int(topic_entry["collected_message_count"]),
        int(topic_entry["unique_sender_count"]),
        int(topic_entry["link_count"]),
        str(topic_entry["last_activity_timestamp"]),
    )


def _should_collapse_topic(topic_entry: Dict[str, object], rank: int, total_topics: int) -> bool:
    low_signal = (
        int(topic_entry["collected_message_count"]) <= 2
        and int(topic_entry["unique_sender_count"]) <= 1
        and int(topic_entry["link_count"]) == 0
        and int(topic_entry["media_count"]) == 0
        and int(topic_entry["service_message_count"]) <= 1
    )
    if total_topics <= 5:
        return False
    return rank >= 5 and low_signal


def _topic_summary_line(topic_entry: Dict[str, object]) -> str:
    return (
        f"{topic_entry['topic_title']}: {topic_entry['collected_message_count']} messages, "
        f"{topic_entry['unique_sender_count']} senders, "
        f"last activity {topic_entry['last_activity_timestamp']}"
    )


def _build_forum_sections(run, raw_messages, candidate_urls: List[str]):
    topic_rows = list_run_forum_topics(run["connection"], run["run_id"])
    grouped_messages = defaultdict(list)
    for row in raw_messages:
        topic_id = row["forum_topic_id"]
        if topic_id is None:
            continue
        grouped_messages[int(topic_id)].append(_raw_row_to_message(row))

    cutoff = _run_started_at(run) - timedelta(hours=int(run["lookback_hours"]))
    active_topic_rows = [
        row for row in topic_rows if _is_active_forum_topic(row, grouped_messages, cutoff)
    ]
    topic_entries: List[Dict[str, object]] = []
    for row in active_topic_rows:
        topic_id = int(row["forum_topic_id"])
        topic_messages = grouped_messages.get(topic_id, [])
        unique_senders = {message["sender_name"] or "Unknown" for message in topic_messages}
        collected_message_count = len(topic_messages)
        last_activity_timestamp = row["forum_topic_date"]
        if topic_messages:
            last_activity_timestamp = max(
                [str(message["message_timestamp"]) for message in topic_messages]
                + [str(last_activity_timestamp)]
            )

        topic_entries.append(
            {
                "topic_id": topic_id,
                "topic_title": row["forum_topic_title"],
                "top_message_id": row["forum_topic_top_message_id"],
                "collected_message_count": collected_message_count,
                "unique_sender_count": len(unique_senders),
                "last_activity_timestamp": last_activity_timestamp,
                "unread_count": int(row["unread_count"]),
                "unread_mentions_count": int(row["unread_mentions_count"]),
                "unread_reactions_count": int(row["unread_reactions_count"]),
                "link_count": sum(1 for message in topic_messages if message["has_links"]),
                "media_count": sum(1 for message in topic_messages if message["has_media"]),
                "service_message_count": sum(
                    1 for message in topic_messages if message["is_service_message"]
                ),
                "is_pinned": bool(row["is_pinned"]),
                "is_closed": bool(row["is_closed"]),
                "is_hidden": bool(row["is_hidden"]),
                "messages": topic_messages,
            }
        )

    sorted_topics = sorted(topic_entries, key=_forum_topic_priority, reverse=True)
    topic_groups: List[Dict[str, object]] = []
    other_activity: List[Dict[str, object]] = []
    for rank, topic_entry in enumerate(sorted_topics):
        collapsed = _should_collapse_topic(topic_entry, rank, len(sorted_topics))
        topic_entry["collapsed"] = collapsed
        if collapsed:
            other_activity.append(
                {
                    "topic_id": topic_entry["topic_id"],
                    "topic_title": topic_entry["topic_title"],
                    "summary": _topic_summary_line(topic_entry),
                    "collected_message_count": topic_entry["collected_message_count"],
                }
            )
            continue

        normal_messages = [
            message for message in topic_entry["messages"] if not message["is_service_message"]
        ]
        service_messages = [
            message for message in topic_entry["messages"] if message["is_service_message"]
        ]
        topic_groups.append(
            {
                **topic_entry,
                "excerpt_messages": normal_messages[-5:],
                "service_messages": service_messages[-3:],
            }
        )

    forum_overview = {
        "forum_display_name": run["target_display_name"],
        "run_id": run["run_id"],
        "total_topics_seen": len(topic_rows),
        "active_topics_seen": len(active_topic_rows),
        "active_topics_collected": sum(
            1 for topic_entry in sorted_topics if int(topic_entry["collected_message_count"]) > 0
        ),
        "significant_topics": len(topic_groups),
        "total_collected_messages": len(raw_messages),
        "candidate_url_count": len(candidate_urls),
    }
    return forum_overview, sorted_topics, topic_groups, other_activity


def build_summary_bundle(connection, run_id: str) -> SummaryBundle:
    run = get_run_with_target(connection, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} does not exist.")

    raw_messages = list_raw_messages(connection, run_id)
    messages, candidate_urls, sender_stats, reply_threads = _base_bundle_parts(raw_messages)
    run_payload = {
        "run_id": run["run_id"],
        "status": run["status"],
        "mode": run["mode"],
        "target_mode": run["target_mode"] or "chat",
        "lookback_hours": run["lookback_hours"],
        "message_count": run["message_count"],
        "started_at": run["started_at"],
        "forum_topic_count": run["forum_topic_count"],
        "forum_active_topic_count": run["forum_active_topic_count"],
    }
    target_payload = {
        "target_id": run["target_id"],
        "target_key": run["target_key"],
        "telegram_entity_id": run["telegram_entity_id"],
        "telegram_entity_type": run["telegram_entity_type"],
        "display_name": run["target_display_name"],
        "is_forum": (run["target_mode"] or "chat") == "forum",
    }

    forum_overview = None
    topic_index: List[Dict[str, object]] = []
    topic_groups: List[Dict[str, object]] = []
    other_activity: List[Dict[str, object]] = []
    if target_payload["is_forum"]:
        forum_run = dict(run)
        forum_run["connection"] = connection
        forum_overview, topic_index, topic_groups, other_activity = _build_forum_sections(
            forum_run,
            raw_messages,
            candidate_urls,
        )

    return SummaryBundle(
        run=run_payload,
        target=target_payload,
        messages=messages,
        candidate_urls=candidate_urls,
        sender_stats=sender_stats,
        reply_threads=reply_threads,
        forum_overview=forum_overview,
        topic_index=topic_index,
        topic_groups=topic_groups,
        other_activity=other_activity,
    )


def bundle_to_json(bundle: SummaryBundle) -> str:
    return json.dumps(
        {
            "run": bundle.run,
            "target": bundle.target,
            "messages": bundle.messages,
            "candidate_urls": bundle.candidate_urls,
            "sender_stats": [
                {"sender_name": stat.sender_name, "message_count": stat.message_count}
                for stat in bundle.sender_stats
            ],
            "reply_threads": bundle.reply_threads,
            "forum_overview": bundle.forum_overview,
            "topic_index": bundle.topic_index,
            "topic_groups": bundle.topic_groups,
            "other_activity": bundle.other_activity,
        },
        indent=2,
        sort_keys=True,
    )


def _bundle_target_metadata_lines(bundle: SummaryBundle) -> List[str]:
    return [
        "## Target Metadata",
        f"- Display Name: {bundle.target['display_name']}",
        f"- Target Key: {bundle.target['target_key']}",
        f"- Entity Type: {bundle.target['telegram_entity_type'] or 'unknown'}",
        f"- Telegram Entity ID: {bundle.target['telegram_entity_id'] or 'unknown'}",
        f"- Forum Enabled: {'yes' if bundle.target['is_forum'] else 'no'}",
        "",
        "## Run Metadata",
        f"- Run ID: {bundle.run['run_id']}",
        f"- Status: {bundle.run['status']}",
        f"- Mode: {bundle.run['mode'] or 'unknown'}",
        f"- Target Mode: {bundle.run['target_mode']}",
        f"- Lookback Hours: {bundle.run['lookback_hours']}",
        f"- Message Count: {bundle.run['message_count']}",
    ]


def _forum_bundle_to_markdown(bundle: SummaryBundle) -> str:
    lines = [f"# Summary Input for {bundle.target['display_name']}", ""]
    lines.extend(_bundle_target_metadata_lines(bundle))
    if bundle.forum_overview is not None:
        lines.extend(
            [
                f"- Topics Seen: {bundle.forum_overview['total_topics_seen']}",
                f"- Active Topics Seen: {bundle.forum_overview['active_topics_seen']}",
                f"- Active Topics Collected: {bundle.forum_overview['active_topics_collected']}",
                "",
                "## Forum Overview",
                f"- Forum Display Name: {bundle.forum_overview['forum_display_name']}",
                f"- Total Topics Seen: {bundle.forum_overview['total_topics_seen']}",
                f"- Active Topics Seen: {bundle.forum_overview['active_topics_seen']}",
                f"- Active Topics Collected: {bundle.forum_overview['active_topics_collected']}",
                f"- Significant Topics: {bundle.forum_overview['significant_topics']}",
                f"- Total Collected Messages: {bundle.forum_overview['total_collected_messages']}",
            ]
        )

    lines.extend(["", "## Topic Radar"])
    if bundle.topic_index:
        for topic in bundle.topic_index:
            collapsed_suffix = " [collapsed]" if topic["collapsed"] else ""
            lines.append(
                f"- {topic['topic_title']}{collapsed_suffix}: "
                f"{topic['collected_message_count']} messages, "
                f"{topic['unique_sender_count']} senders, "
                f"{topic['link_count']} links, "
                f"last activity {topic['last_activity_timestamp']}"
            )
    else:
        lines.append("- No active topics matched this run")

    lines.extend(["", "## Candidate URLs"])
    if bundle.candidate_urls:
        lines.extend(f"- {url}" for url in bundle.candidate_urls)
    else:
        lines.append("- None")

    lines.extend(["", "## Topic Excerpts"])
    if bundle.topic_groups:
        for topic in bundle.topic_groups:
            lines.extend(
                [
                    f"### {topic['topic_title']}",
                    f"- Topic ID: {topic['topic_id']}",
                    f"- Top Message ID: {topic['top_message_id']}",
                    f"- Metrics: {topic['collected_message_count']} messages, "
                    f"{topic['unique_sender_count']} senders, "
                    f"{topic['service_message_count']} service messages",
                ]
            )
            if topic["excerpt_messages"]:
                lines.append("- Discussion Excerpts:")
                for message in topic["excerpt_messages"]:
                    sender_name = message["sender_name"] or "Unknown"
                    body = message["text_content"] or "[no text]"
                    lines.append(
                        f"  - {message['message_timestamp']} | {sender_name} | "
                        f"#{message['telegram_message_id']} | {body}"
                    )
            else:
                lines.append("- Discussion Excerpts: None")
            if topic["service_messages"]:
                lines.append("- Service Events:")
                for message in topic["service_messages"]:
                    body = message["text_content"] or "[service message without text]"
                    lines.append(
                        f"  - {message['message_timestamp']} | "
                        f"#{message['telegram_message_id']} | {body}"
                    )
            lines.append("")
    else:
        lines.append("- No topic excerpts were retained for this run")

    lines.extend(["## Other Activity"])
    if bundle.other_activity:
        lines.extend(f"- {entry['summary']}" for entry in bundle.other_activity)
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def bundle_to_markdown(bundle: SummaryBundle) -> str:
    if bundle.target["is_forum"]:
        return _forum_bundle_to_markdown(bundle)

    lines = [f"# Summary Input for {bundle.target['display_name']}", ""]
    lines.extend(_bundle_target_metadata_lines(bundle))
    lines.extend(["", "## Candidate URLs"])
    if bundle.candidate_urls:
        lines.extend(f"- {url}" for url in bundle.candidate_urls)
    else:
        lines.append("- None")

    lines.extend(["", "## Sender Statistics"])
    if bundle.sender_stats:
        lines.extend(f"- {stat.sender_name}: {stat.message_count}" for stat in bundle.sender_stats)
    else:
        lines.append("- No messages collected")

    lines.extend(["", "## Full Chronological Messages"])
    if bundle.messages:
        for message in bundle.messages:
            sender_name = message["sender_name"] or "Unknown"
            body = message["text_content"] or "[no text]"
            lines.append(
                f"- {message['message_timestamp']} | {sender_name} | "
                f"#{message['telegram_message_id']} | {body}"
            )
    else:
        lines.append("- No messages staged for this run")
    return "\n".join(lines) + "\n"


def write_summary_bundle(
    connection,
    *,
    run_id: str,
    output_format: str,
    output_path: Optional[Path] = None,
) -> Tuple[SummaryBundle, Dict[str, Optional[Path]]]:
    bundle = build_summary_bundle(connection, run_id)
    outputs: Dict[str, Optional[Path]] = {"json": None, "markdown": None}

    if output_format not in {"json", "markdown", "both"}:
        raise ValueError("output_format must be one of: json, markdown, both")

    if output_format in {"json", "both"}:
        json_path = output_path
        if output_format == "both":
            if output_path is None:
                raise ValueError("An output path prefix is required when writing both formats.")
            json_path = _derived_output_path(output_path, ".json")
        if json_path is not None:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(bundle_to_json(bundle), encoding="utf-8")
            outputs["json"] = json_path

    if output_format in {"markdown", "both"}:
        markdown_path = output_path
        if output_format == "both":
            markdown_path = _derived_output_path(output_path, ".md")
        if markdown_path is not None:
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(bundle_to_markdown(bundle), encoding="utf-8")
            outputs["markdown"] = markdown_path

    return bundle, outputs

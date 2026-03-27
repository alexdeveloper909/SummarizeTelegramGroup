from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .collection import URL_PATTERN
from .models import SenderStat, SummaryBundle
from .db import get_run_with_target, list_raw_messages


def build_summary_bundle(connection, run_id: str) -> SummaryBundle:
    run = get_run_with_target(connection, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} does not exist.")

    raw_messages = list_raw_messages(connection, run_id)
    messages: List[Dict[str, object]] = []
    candidate_urls: List[str] = []
    seen_urls = set()
    sender_counter: Counter[str] = Counter()
    reply_threads = defaultdict(list)

    for row in raw_messages:
        message = {
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
        }
        messages.append(message)

        sender_name = row["sender_name"] or "Unknown"
        sender_counter[sender_name] += 1
        if row["reply_to_message_id"] is not None:
            reply_threads[str(row["reply_to_message_id"])].append(int(row["telegram_message_id"]))

        for match in URL_PATTERN.findall(row["text_content"]):
            if match not in seen_urls:
                seen_urls.add(match)
                candidate_urls.append(match)

    sender_stats = [SenderStat(sender_name=name, message_count=count) for name, count in sender_counter.most_common()]
    return SummaryBundle(
        run={
            "run_id": run["run_id"],
            "status": run["status"],
            "mode": run["mode"],
            "lookback_hours": run["lookback_hours"],
            "message_count": run["message_count"],
            "started_at": run["started_at"],
        },
        target={
            "target_id": run["target_id"],
            "target_key": run["target_key"],
            "telegram_entity_id": run["telegram_entity_id"],
            "telegram_entity_type": run["telegram_entity_type"],
            "display_name": run["target_display_name"],
        },
        messages=messages,
        candidate_urls=candidate_urls,
        sender_stats=sender_stats,
        reply_threads=dict(reply_threads),
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
        },
        indent=2,
        sort_keys=True,
    )


def bundle_to_markdown(bundle: SummaryBundle) -> str:
    lines = [
        f"# Summary Input for {bundle.target['display_name']}",
        "",
        "## Run Metadata",
        f"- Run ID: {bundle.run['run_id']}",
        f"- Status: {bundle.run['status']}",
        f"- Mode: {bundle.run['mode'] or 'unknown'}",
        f"- Lookback Hours: {bundle.run['lookback_hours']}",
        f"- Message Count: {bundle.run['message_count']}",
        "",
        "## Candidate URLs",
    ]
    if bundle.candidate_urls:
        lines.extend(f"- {url}" for url in bundle.candidate_urls)
    else:
        lines.append("- None")

    lines.extend(["", "## Sender Statistics"])
    if bundle.sender_stats:
        lines.extend(f"- {stat.sender_name}: {stat.message_count}" for stat in bundle.sender_stats)
    else:
        lines.append("- No messages collected")

    lines.extend(["", "## Chronological Messages"])
    if bundle.messages:
        for message in bundle.messages:
            sender_name = message["sender_name"] or "Unknown"
            body = message["text_content"] or "[no text]"
            lines.append(
                f"- {message['message_timestamp']} | {sender_name} | #{message['telegram_message_id']} | {body}"
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
            json_path = output_path.with_suffix(".json")
        if json_path is not None:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(bundle_to_json(bundle), encoding="utf-8")
            outputs["json"] = json_path

    if output_format in {"markdown", "both"}:
        markdown_path = output_path
        if output_format == "both":
            markdown_path = output_path.with_suffix(".md")
        if markdown_path is not None:
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(bundle_to_markdown(bundle), encoding="utf-8")
            outputs["markdown"] = markdown_path

    return bundle, outputs

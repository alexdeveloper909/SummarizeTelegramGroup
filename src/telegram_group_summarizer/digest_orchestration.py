from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .collection import collect_messages_for_run, normalize_datetime
from .config import AppConfig
from .db import get_run_with_target
from .digest_config import DigestRuntimeOptions
from .report_context import prepare_report_context
from .report_layout import artifact_directory_path


def _timestamp_token(value: datetime) -> str:
    return normalize_datetime(value).strftime("%Y%m%dT%H%M%SZ")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "digest"


def default_digest_manifest_path(
    reports_dir: Path,
    *,
    started_at: datetime,
    job_name: str,
) -> Path:
    filename = f"{_slugify(job_name)}_{_timestamp_token(started_at)}.digest_manifest.json"
    return artifact_directory_path(
        reports_dir,
        normalize_datetime(started_at).isoformat(),
        "draft",
    ) / filename


async def collect_digest_context(
    *,
    connection,
    telegram_client,
    config: AppConfig,
    runtime_options: DigestRuntimeOptions,
    output_path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> tuple[dict[str, Any], Path]:
    started_at = normalize_datetime(now or datetime.now(timezone.utc))
    manifest_targets: list[dict[str, Any]] = []
    prepared_count = 0
    failed_count = 0

    for target in runtime_options.targets:
        target_entry: dict[str, Any] = {
            "target": target.target,
            "label": target.label,
            "target_mode": target.target_mode,
            "max_messages": target.max_messages,
            "forum_topic_limit": target.forum_topic_limit,
            "forum_topic_probe_messages": target.forum_topic_probe_messages,
            "forum_max_messages_per_topic": target.forum_max_messages_per_topic,
        }
        try:
            collect_result = await collect_messages_for_run(
                connection=connection,
                telegram_client=telegram_client,
                target_value=target.target,
                lookback_hours=runtime_options.lookback_hours,
                max_messages=target.max_messages,
                config=config,
                now=started_at,
                target_mode=target.target_mode,
                collection_strategy=runtime_options.collection_strategy,
                forum_topic_limit=target.forum_topic_limit,
                forum_topic_probe_messages=(target.forum_topic_probe_messages or 3),
                forum_max_messages_per_topic=(target.forum_max_messages_per_topic or 50),
            )
            report_context = prepare_report_context(
                connection,
                run_id=str(collect_result["run_id"]),
                config=config,
                report_language=runtime_options.report_language,
            )
            run = get_run_with_target(connection, str(collect_result["run_id"]))
            manifest_targets.append(
                {
                    **target_entry,
                    "status": "prepared",
                    "run_id": collect_result["run_id"],
                    "resolved_target_key": collect_result["target_key"],
                    "resolved_display_name": (
                        run["target_display_name"] if run is not None else None
                    ),
                    "message_count": collect_result["message_count"],
                    "mode": collect_result["mode"],
                    "summary_json_path": report_context["summary_json_path"],
                    "summary_markdown_path": report_context["summary_markdown_path"],
                    "report_prompt_path": report_context["report_prompt_path"],
                }
            )
            prepared_count += 1
        except Exception as exc:
            manifest_targets.append(
                {
                    **target_entry,
                    "status": "failed",
                    "error_summary": str(exc),
                }
            )
            failed_count += 1

    manifest = {
        "job_name": runtime_options.name,
        "started_at": started_at.isoformat(),
        "report_language": runtime_options.report_language,
        "delivery_target": runtime_options.delivery_target,
        "lookback_hours": runtime_options.lookback_hours,
        "max_messages": runtime_options.max_messages,
        "collection_strategy": runtime_options.collection_strategy,
        "prepared_target_count": prepared_count,
        "failed_target_count": failed_count,
        "targets": manifest_targets,
    }

    final_output_path = output_path or default_digest_manifest_path(
        config.reports_dir,
        started_at=started_at,
        job_name=runtime_options.name,
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest, final_output_path

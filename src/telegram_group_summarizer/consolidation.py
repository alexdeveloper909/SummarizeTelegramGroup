from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .collection import normalize_datetime
from .db import get_generated_report, get_run_with_target
from .report_layout import artifact_directory_path


class ConsolidationError(ValueError):
    pass


def load_digest_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConsolidationError("Digest manifest must be a JSON object.")
    if not isinstance(payload.get("targets"), list):
        raise ConsolidationError("Digest manifest must contain a targets list.")
    return payload


def _manifest_started_at(manifest: dict[str, Any]) -> datetime:
    raw_started_at = manifest.get("started_at")
    if not isinstance(raw_started_at, str) or not raw_started_at:
        raise ConsolidationError("Digest manifest is missing started_at.")
    return normalize_datetime(datetime.fromisoformat(raw_started_at))


def default_consolidated_report_path(reports_dir: Path, manifest: dict[str, Any]) -> Path:
    started_at = _manifest_started_at(manifest)
    date_token = started_at.strftime("%Y-%m-%d")
    return artifact_directory_path(reports_dir, started_at.isoformat(), "final") / (
        f"telegram_groups_consolidated_summary_{date_token}.md"
    )


def default_consolidated_prompt_path(reports_dir: Path, manifest: dict[str, Any]) -> Path:
    started_at = _manifest_started_at(manifest)
    date_token = started_at.strftime("%Y-%m-%d")
    return artifact_directory_path(reports_dir, started_at.isoformat(), "report_prompt") / (
        f"telegram_groups_consolidated_summary_{date_token}.report_prompt.md"
    )


def build_consolidated_markdown(connection, manifest: dict[str, Any]) -> str:
    started_at = _manifest_started_at(manifest)
    targets = manifest["targets"]
    included_sections: list[str] = []
    missing_sections: list[str] = []

    for target in targets:
        status = target.get("status")
        label = target.get("label") or target.get("resolved_display_name") or target.get("target")
        if status != "prepared":
            error_summary = target.get("error_summary", "unknown error")
            missing_sections.append(
                f"- {label}: failed before report generation. Reason: {error_summary}"
            )
            continue

        run_id = target.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            missing_sections.append(f"- {label}: prepared target is missing run_id.")
            continue

        report = get_generated_report(connection, run_id)
        run = get_run_with_target(connection, run_id)
        if report is None:
            missing_sections.append(f"- {label}: report has not been stored yet.")
            continue

        source_target_key = target.get("resolved_target_key") or (
            run["target_key"] if run else target.get("target")
        )
        source_mode = target.get("target_mode") or (run["target_mode"] if run else "auto")
        resolved_name = target.get("resolved_display_name") or (
            run["target_display_name"] if run else label
        )
        report_body = str(report["report_markdown"]).strip()
        included_sections.extend(
            [
                f"## {label}",
                f"- Source target: {resolved_name}",
                f"- Target key: {source_target_key}",
                f"- Target mode: {source_mode}",
                f"- Run ID: {run_id}",
                "",
                report_body,
                "",
            ]
        )

    lines = [
        "# Consolidated Telegram Digest",
        "",
        f"- Job Name: {manifest.get('job_name', 'Daily digest')}",
        f"- Generated At (UTC): {started_at.isoformat()}",
        f"- Lookback Hours: {manifest.get('lookback_hours', 'unknown')}",
        f"- Collection Strategy: {manifest.get('collection_strategy', 'unknown')}",
        f"- Report Language: {manifest.get('report_language', 'unknown')}",
        f"- Prepared Targets: {manifest.get('prepared_target_count', 0)}",
        f"- Failed Targets: {manifest.get('failed_target_count', 0)}",
    ]
    if manifest.get("delivery_target"):
        lines.append(f"- Delivery Target: {manifest['delivery_target']}")

    lines.extend(["", "## Included Group Reports"])
    if included_sections:
        lines.extend(included_sections)
    else:
        lines.append("- No group reports are available yet.")

    lines.extend(["## Failed or Missing Targets"])
    if missing_sections:
        lines.extend(missing_sections)
    else:
        lines.append("- None")

    return "\n".join(lines).strip() + "\n"


def build_consolidated_publish_prompt(
    manifest: dict[str, Any],
    consolidated_report_path: Path,
) -> str:
    lines = [
        "# Consolidated Publish Brief",
        "",
        "Use the full consolidated Telegram digest to write a channel-ready publication version.",
        "",
        "## Inputs",
        f"- Full consolidated report path: {consolidated_report_path}",
        f"- Language: {manifest.get('report_language', 'Ukrainian')}",
        f"- Delivery target: {manifest.get('delivery_target') or 'not configured'}",
        "",
        "## Output Contract",
        "- Preserve all important information from the full digest.",
        "- Remove low-value repetition, filler, and duplicated framing.",
        (
            "- Keep the result concise enough for a Telegram channel post, "
            "but do not omit important signals."
        ),
        "- Clearly mention any failed or missing source groups if they matter to the reader.",
        "- Write in Markdown that is safe to pass to send_markdown_report.py.",
        "",
        "## Suggested Structure",
        "1. Headline summary",
        "2. Key developments across groups",
        "3. Important links or resources",
        "4. Action items, requests, or risks",
        "5. Missing coverage if needed",
        "",
        "## Editing Rules",
        "- Do not invent facts that are not in the full consolidated digest.",
        "- Merge overlapping items across groups when that improves clarity.",
        "- Preserve concrete details when they materially improve usefulness or accuracy.",
        "- Prefer short, information-dense bullets over long narrative recap.",
        "",
    ]
    return "\n".join(lines)


def write_consolidated_outputs(
    *,
    connection,
    manifest: dict[str, Any],
    reports_dir: Path,
    output_path: Optional[Path] = None,
    prompt_output_path: Optional[Path] = None,
) -> dict[str, str]:
    consolidated_path = output_path or default_consolidated_report_path(reports_dir, manifest)
    consolidated_path.parent.mkdir(parents=True, exist_ok=True)
    consolidated_path.write_text(
        build_consolidated_markdown(connection, manifest),
        encoding="utf-8",
    )

    final_prompt_path = prompt_output_path or default_consolidated_prompt_path(
        reports_dir,
        manifest,
    )
    final_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    final_prompt_path.write_text(
        build_consolidated_publish_prompt(manifest, consolidated_path),
        encoding="utf-8",
    )

    return {
        "consolidated_report_path": str(consolidated_path),
        "publish_prompt_path": str(final_prompt_path),
    }

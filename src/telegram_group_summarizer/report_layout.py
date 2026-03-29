from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPORT_DATE_FORMAT = "%d.%m.%Y"
REPORT_ARTIFACT_DIRECTORIES = ("final", "report", "report_prompt", "summary", "draft")
RUN_ARTIFACT_PATTERN = re.compile(r"^(?P<run_id>[0-9a-f]{32})(?P<suffix>\..+)$")


@dataclass(frozen=True)
class ReportArtifactPlacement:
    run_id: str
    artifact_directory: str
    filename: str


def _parse_timestamp(timestamp: str) -> datetime:
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def report_date_folder_name(started_at: str) -> str:
    return _parse_timestamp(started_at).strftime(REPORT_DATE_FORMAT)


def report_date_directory(reports_dir: Path, started_at: str) -> Path:
    return reports_dir / report_date_folder_name(started_at)


def ensure_report_date_directories(reports_dir: Path, started_at: str) -> dict[str, Path]:
    date_root = report_date_directory(reports_dir, started_at)
    paths = {}
    for directory_name in REPORT_ARTIFACT_DIRECTORIES:
        path = date_root / directory_name
        path.mkdir(parents=True, exist_ok=True)
        paths[directory_name] = path
    return paths


def artifact_directory_path(reports_dir: Path, started_at: str, artifact_directory: str) -> Path:
    if artifact_directory not in REPORT_ARTIFACT_DIRECTORIES:
        raise ValueError(f"Unsupported report artifact directory: {artifact_directory}")
    return ensure_report_date_directories(reports_dir, started_at)[artifact_directory]


def default_summary_output_prefix(reports_dir: Path, run_id: str, started_at: str) -> Path:
    return artifact_directory_path(reports_dir, started_at, "summary") / f"{run_id}.summary"


def default_report_prompt_path(reports_dir: Path, run_id: str, started_at: str) -> Path:
    return artifact_directory_path(reports_dir, started_at, "report_prompt") / (
        f"{run_id}.report_prompt.md"
    )


def default_report_path(reports_dir: Path, run_id: str, started_at: str) -> Path:
    return artifact_directory_path(reports_dir, started_at, "report") / f"{run_id}.report.md"


def classify_legacy_report_file(path: Path) -> Optional[ReportArtifactPlacement]:
    match = RUN_ARTIFACT_PATTERN.match(path.name)
    if match is None:
        return None

    run_id = match.group("run_id")
    suffix = match.group("suffix")
    if suffix in {".summary.json", ".json"}:
        return ReportArtifactPlacement(
            run_id=run_id,
            artifact_directory="summary",
            filename=f"{run_id}.summary.json",
        )
    if suffix in {".summary.md", ".md"}:
        return ReportArtifactPlacement(
            run_id=run_id,
            artifact_directory="summary",
            filename=f"{run_id}.summary.md",
        )
    if suffix == ".report_prompt.md":
        return ReportArtifactPlacement(
            run_id=run_id,
            artifact_directory="report_prompt",
            filename=path.name,
        )
    if suffix == ".report.md":
        return ReportArtifactPlacement(
            run_id=run_id,
            artifact_directory="report",
            filename=path.name,
        )
    if suffix == ".final.md" or suffix == ".agent_report.md":
        return ReportArtifactPlacement(
            run_id=run_id,
            artifact_directory="final",
            filename=path.name,
        )
    if ".draft." in suffix and suffix.endswith(".md"):
        return ReportArtifactPlacement(
            run_id=run_id,
            artifact_directory="draft",
            filename=path.name,
        )
    return None

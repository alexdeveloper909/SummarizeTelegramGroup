from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import AppConfig
from .db import create_generated_report, get_run_with_target, update_run_status
from .report_layout import default_report_path

REPORT_SECTION_TITLES = [
    "Headline summary",
    "Key topics and signals",
    "Important links",
    "Action items or follow-ups",
]


def store_report(
    connection,
    *,
    run_id: str,
    report_markdown: str,
    config: AppConfig,
    output_path: Optional[Path] = None,
) -> Path:
    run = get_run_with_target(connection, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} does not exist.")

    final_output_path = output_path or default_report_path(
        config.reports_dir,
        run_id,
        str(run["started_at"]),
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_text(report_markdown, encoding="utf-8")

    create_generated_report(
        connection,
        run_id=run_id,
        target_id=int(run["target_id"]),
        report_markdown=report_markdown,
        output_path=str(final_output_path),
    )
    update_run_status(
        connection, run_id, status="summarized", report_output_path=str(final_output_path)
    )
    return final_output_path

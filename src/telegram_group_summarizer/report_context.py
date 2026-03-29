from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from .config import AppConfig
from .db import get_run_with_target
from .report_layout import default_summary_output_prefix
from .report_prompt import DEFAULT_REPORT_LANGUAGE, write_report_prompt
from .summary_input import write_summary_bundle


def prepare_report_context(
    connection,
    *,
    run_id: str,
    config: AppConfig,
    summary_output_prefix: Optional[Path] = None,
    prompt_output_path: Optional[Path] = None,
    report_language: str = DEFAULT_REPORT_LANGUAGE,
) -> Dict[str, object]:
    run = get_run_with_target(connection, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} does not exist.")

    output_prefix = summary_output_prefix or default_summary_output_prefix(
        config.reports_dir,
        run_id,
        str(run["started_at"]),
    )
    bundle, summary_paths = write_summary_bundle(
        connection,
        run_id=run_id,
        output_format="both",
        output_path=output_prefix,
    )
    prompt_path = write_report_prompt(
        bundle,
        output_path=prompt_output_path,
        reports_dir=config.reports_dir,
        report_language=report_language,
    )

    return {
        "run_id": run_id,
        "summary_json_path": str(summary_paths["json"]) if summary_paths["json"] else None,
        "summary_markdown_path": (
            str(summary_paths["markdown"]) if summary_paths["markdown"] else None
        ),
        "report_prompt_path": str(prompt_path),
        "message_count": bundle.run["message_count"],
    }

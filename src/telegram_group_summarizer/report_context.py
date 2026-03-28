from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from .config import AppConfig
from .report_prompt import DEFAULT_REPORT_LANGUAGE, write_report_prompt
from .summary_input import write_summary_bundle


def default_summary_output_prefix(reports_dir: Path, run_id: str) -> Path:
    return reports_dir / f"{run_id}.summary"


def prepare_report_context(
    connection,
    *,
    run_id: str,
    config: AppConfig,
    summary_output_prefix: Optional[Path] = None,
    prompt_output_path: Optional[Path] = None,
    report_language: str = DEFAULT_REPORT_LANGUAGE,
) -> Dict[str, object]:
    output_prefix = summary_output_prefix or default_summary_output_prefix(
        config.reports_dir,
        run_id,
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

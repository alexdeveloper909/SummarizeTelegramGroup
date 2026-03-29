from __future__ import annotations
# ruff: noqa: E402, I001

import argparse
import json
from pathlib import Path

from _bootstrap import ensure_src_on_path

ensure_src_on_path()

from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.logging_utils import configure_logging
from telegram_group_summarizer.report_context import prepare_report_context
from telegram_group_summarizer.report_prompt import DEFAULT_REPORT_LANGUAGE


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare both the summary bundle and report prompt for one run."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--language", default=DEFAULT_REPORT_LANGUAGE)
    parser.add_argument(
        "--summary-output-prefix",
        help="Optional output prefix for the summary bundle files.",
    )
    parser.add_argument(
        "--prompt-output",
        help="Optional output path for the report-writing prompt.",
    )
    args = parser.parse_args()

    config = load_config()
    configure_logging(config.log_level)
    connection = ensure_database(config)
    result = prepare_report_context(
        connection,
        run_id=args.run_id,
        config=config,
        summary_output_prefix=(
            Path(args.summary_output_prefix) if args.summary_output_prefix else None
        ),
        prompt_output_path=Path(args.prompt_output) if args.prompt_output else None,
        report_language=args.language,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

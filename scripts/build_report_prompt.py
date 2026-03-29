from __future__ import annotations
# ruff: noqa: E402, I001

import argparse
from pathlib import Path

from _bootstrap import ensure_src_on_path

ensure_src_on_path()

from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.logging_utils import configure_logging
from telegram_group_summarizer.report_prompt import (
    DEFAULT_REPORT_LANGUAGE,
    build_report_prompt,
    write_report_prompt,
)
from telegram_group_summarizer.summary_input import build_summary_bundle


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a generic report-writing brief for one collected run."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--language", default=DEFAULT_REPORT_LANGUAGE)
    parser.add_argument("--output", help="Optional output path.")
    args = parser.parse_args()

    config = load_config()
    configure_logging(config.log_level)
    connection = ensure_database(config)
    bundle = build_summary_bundle(connection, args.run_id)

    if args.output:
        path = write_report_prompt(
            bundle,
            output_path=Path(args.output),
            reports_dir=config.reports_dir,
            report_language=args.language,
        )
        print(str(path))
        return

    print(build_report_prompt(bundle, report_language=args.language))


if __name__ == "__main__":
    main()

from __future__ import annotations
# ruff: noqa: E402, I001

import argparse
import sys
from pathlib import Path

from _bootstrap import ensure_src_on_path

ensure_src_on_path()

from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.logging_utils import configure_logging
from telegram_group_summarizer.reports import store_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Persist a finalized report for a run.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--input-path", help="Read report Markdown from a file. Defaults to stdin.")
    parser.add_argument("--output-path", help="Optional report output path.")
    args = parser.parse_args()

    config = load_config()
    configure_logging(config.log_level)
    connection = ensure_database(config)

    if args.input_path:
        report_markdown = Path(args.input_path).read_text(encoding="utf-8")
    else:
        report_markdown = sys.stdin.read()
    if not report_markdown.strip():
        raise ValueError("Report content is empty.")

    final_path = store_report(
        connection,
        run_id=args.run_id,
        report_markdown=report_markdown,
        config=config,
        output_path=Path(args.output_path) if args.output_path else None,
    )
    print(str(final_path))


if __name__ == "__main__":
    main()

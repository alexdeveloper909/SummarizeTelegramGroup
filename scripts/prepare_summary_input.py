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
from telegram_group_summarizer.summary_input import (
    bundle_to_json,
    bundle_to_markdown,
    write_summary_bundle,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare summary input for a collected run.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--format", choices=["json", "markdown", "both"], default="markdown")
    parser.add_argument(
        "--output", help="Optional output path. For --format both, this is used as the file prefix."
    )
    args = parser.parse_args()

    config = load_config()
    configure_logging(config.log_level)
    connection = ensure_database(config)

    output_path = Path(args.output) if args.output else None
    bundle, output_paths = write_summary_bundle(
        connection,
        run_id=args.run_id,
        output_format=args.format,
        output_path=output_path,
    )

    if args.output:
        print(
            json.dumps(
                {key: str(value) if value else None for key, value in output_paths.items()},
                sort_keys=True,
            )
        )
        return

    if args.format == "json":
        print(bundle_to_json(bundle))
    elif args.format == "markdown":
        print(bundle_to_markdown(bundle))
    else:
        print(
            json.dumps(
                {"json": bundle_to_json(bundle), "markdown": bundle_to_markdown(bundle)},
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()

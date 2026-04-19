from __future__ import annotations
# ruff: noqa: E402, I001

import argparse
import json
from pathlib import Path

from _bootstrap import ensure_src_on_path

ensure_src_on_path()

from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.consolidation import load_digest_manifest, write_consolidated_outputs
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.logging_utils import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a full consolidated digest from a multi-target digest manifest."
    )
    parser.add_argument("--manifest-path", required=True, help="Path to the digest manifest JSON.")
    parser.add_argument("--output", help="Optional output path for the consolidated Markdown.")
    parser.add_argument(
        "--prompt-output",
        help="Optional output path for the publish-editing prompt Markdown.",
    )
    args = parser.parse_args()

    config = load_config()
    configure_logging(config.log_level)
    connection = ensure_database(config)
    manifest = load_digest_manifest(Path(args.manifest_path))
    result = write_consolidated_outputs(
        connection=connection,
        manifest=manifest,
        reports_dir=config.reports_dir,
        output_path=Path(args.output) if args.output else None,
        prompt_output_path=Path(args.prompt_output) if args.prompt_output else None,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

from __future__ import annotations
# ruff: noqa: E402, I001

import argparse
import asyncio
import json
from pathlib import Path

from _bootstrap import ensure_src_on_path

ensure_src_on_path()

from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.digest_config import (
    load_digest_job_config,
    resolve_digest_runtime_options,
)
from telegram_group_summarizer.digest_orchestration import collect_digest_context
from telegram_group_summarizer.logging_utils import configure_logging
from telegram_group_summarizer.telethon_client import TelethonWorkflowClient, create_telethon_client


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect and prepare multi-target digest context from a JSON config."
    )
    parser.add_argument("--targets-config", required=True, help="Path to the digest JSON config.")
    parser.add_argument("--lookback-hours", type=int, help="Override lookback hours.")
    parser.add_argument("--max-messages", type=int, help="Override default max messages.")
    parser.add_argument(
        "--collection-strategy",
        choices=["unread-first", "lookback-only"],
        help="Override the config collection strategy.",
    )
    parser.add_argument("--language", help="Override report language.")
    parser.add_argument("--delivery-target", help="Override delivery target.")
    parser.add_argument("--output", help="Optional output path for the manifest JSON.")
    args = parser.parse_args()

    config = load_config()
    config.validate_telegram_credentials()
    configure_logging(config.log_level)
    connection = ensure_database(config)
    job_config = load_digest_job_config(Path(args.targets_config))
    runtime_options = resolve_digest_runtime_options(
        job_config,
        lookback_hours=args.lookback_hours,
        max_messages=args.max_messages,
        collection_strategy=args.collection_strategy,
        report_language=args.language,
        delivery_target=args.delivery_target,
    )

    client = create_telethon_client(config)
    async with client:
        workflow_client = TelethonWorkflowClient(client)
        manifest, manifest_path = await collect_digest_context(
            connection=connection,
            telegram_client=workflow_client,
            config=config,
            runtime_options=runtime_options,
            output_path=Path(args.output) if args.output else None,
        )

    payload = {
        "manifest_path": str(manifest_path),
        **manifest,
    }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())

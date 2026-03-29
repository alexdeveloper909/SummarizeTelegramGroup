from __future__ import annotations
# ruff: noqa: E402, I001

import argparse
import asyncio
import json

from _bootstrap import ensure_src_on_path

ensure_src_on_path()

from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.finalization import finalize_run
from telegram_group_summarizer.logging_utils import configure_logging
from telegram_group_summarizer.telethon_client import TelethonWorkflowClient, create_telethon_client


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize a successful Telegram summarization run."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mark-read", action="store_true")
    parser.add_argument("--purge-raw", action="store_true")
    args = parser.parse_args()

    if not args.mark_read and not args.purge_raw:
        raise ValueError("At least one finalization action must be requested.")

    config = load_config()
    configure_logging(config.log_level)
    connection = ensure_database(config)

    if args.mark_read:
        config.validate_telegram_credentials()
        client = create_telethon_client(config)
        async with client:
            workflow_client = TelethonWorkflowClient(client)
            result = await finalize_run(
                connection=connection,
                telegram_client=workflow_client,
                run_id=args.run_id,
                mark_read=args.mark_read,
                purge_raw=args.purge_raw,
            )
    else:
        result = await finalize_run(
            connection=connection,
            telegram_client=None,
            run_id=args.run_id,
            mark_read=False,
            purge_raw=args.purge_raw,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())

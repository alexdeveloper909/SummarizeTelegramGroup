from __future__ import annotations

import argparse
import asyncio
import json
import logging

from telegram_group_summarizer.collection import collect_messages_for_run
from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.logging_utils import configure_logging
from telegram_group_summarizer.telethon_client import TelethonWorkflowClient, create_telethon_client


async def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Telegram messages into SQLite.")
    parser.add_argument(
        "--target", required=True, help="Target key, username, or Telegram entity ID."
    )
    parser.add_argument(
        "--target-mode",
        choices=["auto", "chat", "forum"],
        default="auto",
        help="Target handling mode. Auto-detect forums by default.",
    )
    parser.add_argument("--lookback-hours", type=int, help="Lookback window in hours.")
    parser.add_argument("--max-messages", type=int, help="Maximum number of messages to collect.")
    parser.add_argument(
        "--forum-topic-limit",
        type=int,
        help="Optional cap on forum topics to inspect during one run.",
    )
    parser.add_argument(
        "--forum-topic-probe-messages",
        type=int,
        default=3,
        help="Coverage-pass message count fetched per active forum topic.",
    )
    parser.add_argument(
        "--forum-max-messages-per-topic",
        type=int,
        default=50,
        help="Maximum total collected messages per forum topic.",
    )
    parser.add_argument("--run-id", help="Optional run identifier supplied by the orchestrator.")
    args = parser.parse_args()

    config = load_config()
    config.validate_telegram_credentials()
    configure_logging(config.log_level)

    lookback_hours = args.lookback_hours or config.default_lookback_hours
    max_messages = args.max_messages or config.default_max_messages

    connection = ensure_database(config)
    client = create_telethon_client(config)
    async with client:
        workflow_client = TelethonWorkflowClient(client)
        result = await collect_messages_for_run(
            connection=connection,
            telegram_client=workflow_client,
            target_value=args.target,
            lookback_hours=lookback_hours,
            max_messages=max_messages,
            config=config,
            run_id=args.run_id,
            target_mode=args.target_mode,
            forum_topic_limit=args.forum_topic_limit,
            forum_topic_probe_messages=args.forum_topic_probe_messages,
            forum_max_messages_per_topic=args.forum_max_messages_per_topic,
        )

    logging.getLogger(__name__).info(
        "Collection completed",
        extra={
            "run_id": result["run_id"],
            "target_key": result["target_key"],
            "phase": "collection",
            "status": "collected",
        },
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())

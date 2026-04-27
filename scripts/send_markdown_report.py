from __future__ import annotations
# ruff: noqa: E402, I001

import argparse
import asyncio
import json
import logging
from pathlib import Path

from _bootstrap import ensure_src_on_path

ensure_src_on_path()

from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.db import ensure_database
from telegram_group_summarizer.logging_utils import configure_logging
from telegram_group_summarizer.report_delivery import (
    MAX_TELEGRAM_MESSAGE_UTF16,
    read_markdown_report,
    send_markdown_report,
)
from telegram_group_summarizer.telethon_client import TelethonWorkflowClient, create_telethon_client
from telegram_group_summarizer.telethon_client import create_telethon_bot_client


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send an existing Markdown report to a Telegram chat."
    )
    parser.add_argument("--input-path", required=True, help="Path to the Markdown report to send.")
    parser.add_argument(
        "--target",
        help=(
            "Target key, username, or Telegram entity ID for the destination chat. "
            "Defaults to TELEGRAM_DELIVERY_CHAT_ID when omitted."
        ),
    )
    parser.add_argument("--session-name", help="Override the default Telethon session file name.")
    parser.add_argument(
        "--sender",
        choices=("user", "bot"),
        help="Choose whether to send as the user account or the delivery bot.",
    )
    parser.add_argument(
        "--topic-id",
        type=int,
        help="Forum topic id for topic-thread delivery.",
    )
    parser.add_argument(
        "--link-preview",
        action="store_true",
        help="Allow Telegram link previews in the sent messages.",
    )
    parser.add_argument(
        "--max-message-length",
        type=int,
        default=MAX_TELEGRAM_MESSAGE_UTF16,
        help="Maximum UTF-16 code units per Telegram message chunk.",
    )
    args = parser.parse_args()

    config = load_config()
    sender = args.sender or config.telegram_delivery_mode
    target = args.target or config.telegram_delivery_chat_id
    topic_id = args.topic_id if args.topic_id is not None else config.telegram_delivery_topic_id
    if not target:
        raise ValueError("Missing delivery target: pass --target or set TELEGRAM_DELIVERY_CHAT_ID.")
    if sender == "bot":
        config.validate_telegram_credentials()
        config.validate_bot_delivery_credentials()
        client = create_telethon_bot_client(config, session_name=args.session_name)
    else:
        config.validate_telegram_credentials()
        client = create_telethon_client(config, session_name=args.session_name)

    configure_logging(config.log_level)
    connection = ensure_database(config)
    markdown_text = read_markdown_report(Path(args.input_path))
    await client.connect()
    try:
        if sender == "bot":
            await client.start(bot_token=config.telegram_bot_token)
        workflow_client = TelethonWorkflowClient(client)
        result = await send_markdown_report(
            connection=connection,
            telegram_client=workflow_client,
            target_value=target,
            markdown_text=markdown_text,
            topic_id=topic_id,
            link_preview=args.link_preview,
            max_message_length=args.max_message_length,
        )
    finally:
        await client.disconnect()

    logging.getLogger(__name__).info(
        "Report delivery completed",
        extra={
            "target_key": result["target_key"],
            "topic_id": result.get("topic_id"),
            "sender": sender,
            "phase": "report_delivery",
            "status": "delivered",
        },
    )
    payload = {
        "input_path": str(Path(args.input_path).resolve()),
        **result,
    }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())

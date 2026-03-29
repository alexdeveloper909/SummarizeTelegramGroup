from __future__ import annotations
# ruff: noqa: E402, I001

import argparse
import asyncio

from _bootstrap import ensure_src_on_path

ensure_src_on_path()

from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.logging_utils import configure_logging
from telegram_group_summarizer.telethon_client import create_telethon_client


async def main() -> None:
    parser = argparse.ArgumentParser(description="Authenticate a local Telethon session.")
    parser.add_argument("--session-name", help="Override the default session file name.")
    args = parser.parse_args()

    config = load_config()
    config.validate_telegram_credentials()
    configure_logging(config.log_level)

    client = create_telethon_client(config, session_name=args.session_name)
    await client.connect()
    try:
        await client.start(phone=config.telegram_phone, password=config.telegram_password)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

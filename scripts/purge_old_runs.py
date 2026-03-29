from __future__ import annotations
# ruff: noqa: E402, I001

import argparse
from datetime import datetime, timedelta, timezone

from _bootstrap import ensure_src_on_path

ensure_src_on_path()

from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.db import delete_raw_messages, ensure_database
from telegram_group_summarizer.logging_utils import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge old finalized raw-message staging rows.")
    parser.add_argument(
        "--older-than-hours",
        type=int,
        default=168,
        help="Delete finalized runs older than this age.",
    )
    args = parser.parse_args()

    config = load_config()
    configure_logging(config.log_level)
    connection = ensure_database(config)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.older_than_hours)

    runs = connection.execute(
        """
        SELECT run_id
        FROM collection_runs
        WHERE status = 'finalized'
          AND completed_at IS NOT NULL
          AND completed_at < ?
        """,
        (cutoff.isoformat(),),
    ).fetchall()

    deleted_rows = 0
    for run in runs:
        deleted_rows += delete_raw_messages(connection, run["run_id"])
    print(deleted_rows)


if __name__ == "__main__":
    main()

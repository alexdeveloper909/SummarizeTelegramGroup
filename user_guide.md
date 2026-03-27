# User Guide

This project collects Telegram messages for a single target, stages normalized rows in local SQLite, prepares an agent-friendly summary bundle, stores a final report, and only then marks the Telegram target as read and purges staged raw rows.

Use [docs/specification.md](docs/specification.md) for the detailed contract. Use this guide for setup and normal operations.

## Prerequisites

- Python 3.9 or newer
- A Telegram API ID and API hash from https://my.telegram.org
- A local virtual environment

Recommended setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[telegram,dev]'
```

## Required Environment Variables

- `TELEGRAM_API_ID`: required for `auth_telegram.py`, `collect_messages.py`, and `finalize_run.py --mark-read`
- `TELEGRAM_API_HASH`: required for `auth_telegram.py`, `collect_messages.py`, and `finalize_run.py --mark-read`

Optional environment variables:

- `TELEGRAM_SESSION_NAME`: Telethon session file name, default `telegram_group_summarizer`
- `TELEGRAM_SUMMARIZER_DB_PATH`: SQLite path, default `data/sqlite/telegram_group_summarizer.db`
- `TELEGRAM_SUMMARIZER_REPORTS_DIR`: report directory, default `data/reports`
- `TELEGRAM_SUMMARIZER_SESSIONS_DIR`: session directory, default `data/sessions`
- `TELEGRAM_SUMMARIZER_LOGS_DIR`: logs directory, default `logs`
- `TELEGRAM_SUMMARIZER_DEFAULT_LOOKBACK_HOURS`: default `24`
- `TELEGRAM_SUMMARIZER_MAX_LOOKBACK_HOURS`: default `24`
- `TELEGRAM_SUMMARIZER_DEFAULT_MAX_MESSAGES`: default `500`
- `TELEGRAM_SUMMARIZER_SQLITE_BUSY_TIMEOUT_MS`: default `5000`
- `TELEGRAM_SUMMARIZER_LOG_LEVEL`: default `INFO`

## Telegram Authentication Bootstrap

Run the one-time interactive authentication flow:

```bash
python3 scripts/auth_telegram.py
```

This creates a local Telethon session under `data/sessions/`. Session files are sensitive credentials and must never be committed.

## Manual Collection

Collect unread messages first, with a lookback fallback:

```bash
python3 scripts/collect_messages.py --target team_alpha --lookback-hours 24 --max-messages 500
```

`--target` accepts:

- an existing `report_targets.target_key` alias
- a Telegram username such as `team_alpha` or `@team_alpha`
- a numeric Telegram entity ID such as `-1001234567890`

If an existing alias row is present in SQLite, alias resolution wins over username parsing.

The collector prints a JSON payload including the `run_id`.

## Preparing Summary Input

Build agent-friendly summary input without calling Telegram again:

```bash
python3 scripts/prepare_summary_input.py --run-id <RUN_ID> --format both --output data/reports/<RUN_ID>.summary
```

This writes:

- `data/reports/<RUN_ID>.summary.json`
- `data/reports/<RUN_ID>.summary.md`

If you omit `--output`, the script prints the requested format to stdout.

## Writing the Final Report

The summarization step is agent-driven. Once the report Markdown exists, persist it:

```bash
python3 scripts/store_report.py --run-id <RUN_ID> --input-path report.md
```

By default the report is written to `data/reports/<RUN_ID>.report.md` and also stored in the `generated_reports` table. Automation can capture either the emitted file path or the stored report record.

## Finalization

Only finalize after the report has been stored successfully:

```bash
python3 scripts/finalize_run.py --run-id <RUN_ID> --mark-read --purge-raw
```

Useful variants:

- `python3 scripts/finalize_run.py --run-id <RUN_ID> --purge-raw`
- `python3 scripts/finalize_run.py --run-id <RUN_ID> --mark-read`

`finalize_run.py` refuses to finalize a run that has no stored report.

## End-to-End Dry Run Example

```bash
python3 scripts/auth_telegram.py
python3 scripts/collect_messages.py --target team_alpha --lookback-hours 24 --max-messages 200
python3 scripts/prepare_summary_input.py --run-id <RUN_ID> --format markdown --output data/reports/<RUN_ID>.summary.md
# Agent reads the prepared bundle and writes report.md
python3 scripts/store_report.py --run-id <RUN_ID> --input-path report.md
python3 scripts/finalize_run.py --run-id <RUN_ID> --mark-read --purge-raw
```

## Retry and Recovery

- If collection fails, inspect `collection_runs.error_summary` and rerun collection with a new `run_id` or the same orchestrator-supplied `run_id` strategy.
- If summarization fails, staged raw rows remain in `raw_messages`. Re-run summary preparation and report generation without recollecting Telegram data.
- If finalization fails after the report exists, re-run `scripts/finalize_run.py`. Mark-as-read and raw-row purge are retry-safe.

## Troubleshooting

- Missing credentials: set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.
- Telethon import errors: install project extras with `pip install -e '.[telegram]'`.
- Empty prepared bundle: the target may genuinely have no unread or recent messages inside the lookback window.
- Username or entity resolution failures: authenticate first and confirm the target is reachable from the logged-in Telegram account.
- SQLite lock delays: keep the default WAL mode and busy timeout unless you have a reason to tune them.

## Validation Commands

- `PYTHONPATH=src python3 -m unittest discover -s tests -v`
- `python3 -m compileall src scripts tests`
- `python3 -m ruff check src scripts tests`

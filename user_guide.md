# User Guide

This project collects Telegram messages for a single target, stages normalized rows in local SQLite, prepares an agent-friendly summary bundle, stores a final report, and only then marks the covered Telegram content as read and purges staged raw rows. It also supports an explicit manual step for sending an existing Markdown report into a Telegram chat.

Use [docs/specification.md](docs/specification.md) for the detailed contract. Use this guide for setup and normal operations.

## Prerequisites

- Python 3.10 or newer
- A Telegram API ID and API hash from https://my.telegram.org
- A local virtual environment

Recommended setup:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[telegram,dev]'
```

## Required Environment Variables

- `TELEGRAM_API_ID`: required for `auth_telegram.py`, `collect_messages.py`, and `finalize_run.py --mark-read`
- `TELEGRAM_API_HASH`: required for `auth_telegram.py`, `collect_messages.py`, and `finalize_run.py --mark-read`
- `TELEGRAM_PHONE`: optional for `auth_telegram.py`; if set, the auth flow uses it instead of prompting for the phone number
- `TELEGRAM_PASSWORD`: optional for `auth_telegram.py`; if set, the auth flow uses it for Telegram two-step verification instead of prompting for the password

You can provide these either through the shell environment or a local ignored env file. The loader checks, in order:

- `.secrets/telegram.env`
- `.env.local`
- `.env`

Shell environment variables take precedence over file-based values. Example `.secrets/telegram.env`:

```bash
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_hash_here
TELEGRAM_PHONE=+34123456789
TELEGRAM_PASSWORD=your_2fa_password
```

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

The manual report-delivery script also depends on `telegramify-markdown`, which uses a Python 3.10+ entity-based API.
By default, generated report artifacts are stored under `data/reports/DD.MM.YYYY/` with separate `summary/`, `report_prompt/`, `draft/`, `report/`, and `final/` subfolders.

## Telegram Authentication Bootstrap

Run the one-time interactive authentication flow:

```bash
python3.12 scripts/auth_telegram.py
```

If `TELEGRAM_PHONE` is configured, the script skips the phone-number prompt. If `TELEGRAM_PASSWORD` is also configured, the script also skips the Telegram 2FA password prompt and only asks for the one-time login code.

This creates a local Telethon session under `data/sessions/`. Session files are sensitive credentials and must never be committed.

## Manual Collection

Collect unread messages first, with a lookback fallback:

```bash
python3.12 scripts/collect_messages.py --target team_alpha --lookback-hours 24 --max-messages 500
```

Forum-aware collection uses the same script:

```bash
python3.12 scripts/collect_messages.py \
  --target product_forum \
  --target-mode forum \
  --lookback-hours 24 \
  --max-messages 500 \
  --forum-topic-probe-messages 3 \
  --forum-max-messages-per-topic 50
```

`--target` accepts:

- an existing `report_targets.target_key` alias
- a Telegram username such as `team_alpha` or `@team_alpha`
- a numeric Telegram entity ID such as `-1001234567890`

If an existing alias row is present in SQLite, alias resolution wins over username parsing.

`--target-mode` supports:

- `auto`: default; detect forum-enabled targets automatically
- `chat`: force flat chat/channel behavior
- `forum`: force forum behavior and fail if the target is not forum-enabled

Optional forum tuning flags:

- `--forum-topic-limit`
- `--forum-topic-probe-messages`
- `--forum-max-messages-per-topic`

The collector prints a JSON payload including the `run_id`.

## Preparing Summary Input

Build agent-friendly summary input without calling Telegram again:

```bash
python3.12 scripts/prepare_summary_input.py --run-id <RUN_ID> --format both --output data/reports/DD.MM.YYYY/summary/<RUN_ID>.summary
```

This writes:

- `data/reports/DD.MM.YYYY/summary/<RUN_ID>.summary.json`
- `data/reports/DD.MM.YYYY/summary/<RUN_ID>.summary.md`

If you omit `--output`, the script prints the requested format to stdout.

Preferred combined step:

```bash
python3.12 scripts/prepare_report_context.py --run-id <RUN_ID>
```

This writes the summary bundle and report brief together and prints a JSON payload with the generated file paths plus the collected message count.
Without custom output arguments, the files are written under the run date:

- `data/reports/DD.MM.YYYY/summary/<RUN_ID>.summary.json`
- `data/reports/DD.MM.YYYY/summary/<RUN_ID>.summary.md`
- `data/reports/DD.MM.YYYY/report_prompt/<RUN_ID>.report_prompt.md`

For forum runs, the prepared bundle becomes topic-aware. The Markdown bundle prefers:

- a forum overview
- a ranked topic radar
- compact excerpts for the most important threads
- a short other-activity section for collapsed low-signal topics

## Writing the Final Report

The summarization step is agent-driven. Once the report Markdown exists, persist it:

```bash
python3.12 scripts/store_report.py --run-id <RUN_ID> --input-path report.md
```

By default the report is written to `data/reports/DD.MM.YYYY/report/<RUN_ID>.report.md` and also stored in the `generated_reports` table. Automation can capture either the emitted file path or the stored report record.

To keep report writing consistent, generate a report brief first:

```bash
python3.12 scripts/build_report_prompt.py --run-id <RUN_ID> --output data/reports/DD.MM.YYYY/report_prompt/<RUN_ID>.report_prompt.md
```

This file is meant to be the first input the agent reads. It gives a generic report contract plus run metadata, candidate URLs, and sender statistics before the agent works through the prepared message bundle.

When writing the final report, prefer these rules:

- do not recap everything; focus on the most important information
- preserve concrete details only when they materially improve usefulness or accuracy
- collapse repetition when several messages describe the same situation
- if the stream contains conflicting or weakly supported claims, keep the main report conservative

## Sending a Stored Report to Telegram

This is a separate manual step. It is not part of the default collection, preparation, storage, or finalization flow.

Use it only when you explicitly want to deliver an already-written Markdown file to a Telegram chat:

```bash
python3.12 scripts/send_markdown_report.py \
  --input-path telegram_groups_consolidated_summary_2026-03-28.md \
  --target -1003572938359
```

Behavior:

- reads an existing Markdown file from disk
- converts it with `telegramify-markdown`
- splits oversized content into multiple Telegram-safe messages
- sends the chunks sequentially through the existing Telethon session

The script does not alter collection-run state. It does not mark chats as read, purge raw rows, or auto-run after report generation.

## Finalization

Only finalize after the report has been stored successfully:

```bash
python3.12 scripts/finalize_run.py --run-id <RUN_ID> --mark-read --purge-raw
```

Useful variants:

- `python3.12 scripts/finalize_run.py --run-id <RUN_ID> --purge-raw`
- `python3.12 scripts/finalize_run.py --run-id <RUN_ID> --mark-read`

`finalize_run.py` refuses to finalize a run that has no stored report.
For forum runs, `--mark-read` acknowledges only the collected topic threads; it does not mark the entire forum as read.

## End-to-End Dry Run Example

```bash
python3.12 scripts/auth_telegram.py
python3.12 scripts/collect_messages.py --target team_alpha --lookback-hours 24 --max-messages 200
python3.12 scripts/prepare_report_context.py --run-id <RUN_ID>
# Agent reads the prepared bundle and writes report.md
python3.12 scripts/store_report.py --run-id <RUN_ID> --input-path report.md
python3.12 scripts/finalize_run.py --run-id <RUN_ID> --mark-read --purge-raw
```

Example final-report shape:

```markdown
Source target: Team Alpha (channel, target key: team_alpha)

# Headline summary

Two or three sentences on the most useful outcomes from the chat.

## Why this matters

One short paragraph describing why these signals deserve attention.

## Key topics and signals

- Important developments or noteworthy themes from the message stream
- Concrete details that help the reader act on the information
- Distinct items grouped without repeating the same situation multiple times

## Important links

- One or more URLs worth opening later

## Action items or follow-ups

- Practical next steps for the user
```

## Retry and Recovery

- If collection fails, inspect `collection_runs.error_summary` and rerun collection with a new `run_id` or the same orchestrator-supplied `run_id` strategy.
- If summarization fails, staged raw rows remain in `raw_messages`. Re-run summary preparation and report generation without recollecting Telegram data.
- If finalization fails after the report exists, re-run `scripts/finalize_run.py`. Mark-as-read and raw-row purge are retry-safe.

## Troubleshooting

- Missing credentials: set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.
- Telethon import errors: install project extras with `pip install -e '.[telegram]'`.
- Report-delivery import errors: ensure you created the environment with Python 3.10+ and installed `.[telegram]`.
- Empty prepared bundle: the target may genuinely have no unread or recent messages inside the lookback window.
- Username or entity resolution failures: authenticate first and confirm the target is reachable from the logged-in Telegram account.
- SQLite lock delays: keep the default WAL mode and busy timeout unless you have a reason to tune them.

## Report Layout Migration

If you still have older flat files directly under `data/reports/`, normalize them with:

```bash
PYTHONPATH=src python3.12 scripts/migrate_report_layout.py
```

Use `--dry-run` first if you want to preview the moves.

## Validation Commands

- `PYTHONPATH=src python3.12 -m unittest discover -s tests -v`
- `python3.12 -m compileall src scripts tests`
- `python3.12 -m ruff check src scripts tests`

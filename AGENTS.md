# AGENTS.md

## Project Overview

This repository is building toward an automation-oriented Telegram group summarizer. Agents running here are expected to help implement and operate a pipeline that:

- collects Telegram messages through local Python scripts
- stores normalized message data in local SQLite
- prepares agent-friendly summary input
- produces a concise report from the prepared data
- finalizes the run by marking the Telegram target as read and purging staged raw data
- optionally delivers an already-written report to a chosen Telegram chat when explicitly requested

The repository now contains a working local pipeline for both flat Telegram targets and forum-enabled supergroups. Read the documentation before writing code.

## Required Reading Order

1. `PROJECT_OVERVIEW.md`
2. `docs/specification.md`
3. `user_guide.md`

If implementation-specific docs are later added under `docs/`, prefer the most specific document relevant to the task.

## Working Rules

- Treat `docs/specification.md` as the current source of truth for scope and architecture.
- Treat `docs/forum_support_specification.md` as the source of truth for forum-aware collection, bundle shaping, and finalization behavior.
- Keep data collection separate from summarization logic.
- Do not add hidden constants for Telegram targets, secrets, or local paths.
- Prefer explicit CLI arguments and environment variables.
- For multi-target digests, keep target lists in an explicit JSON config file rather than hard-coding them into prompts or scripts.
- Keep raw Telegram data retention minimal.
- Do not mark Telegram messages as read until a report has been successfully produced.
- For forum runs, never replace topic-scoped read acknowledgement with chat-wide read acknowledgement.
- Do not purge staged raw data on failed runs.
- Keep report delivery separate from the default summarization flow; do not add automatic outbound sending unless the user explicitly requests that scope change.
- Do not hard-code delivery targets; prefer explicit CLI arguments and environment variables.
- Keep report artifacts under `data/reports/DD.MM.YYYY/` and use the standard subfolders: `summary`, `report_prompt`, `draft`, `report`, and `final`.

## Security Notes

- Telethon session files are sensitive credentials and must never be committed.
- Preferred local secret file for Telegram credentials is `.secrets/telegram.env` when shell exports are not practical.
- `TELEGRAM_PHONE` may be stored alongside API credentials to avoid interactive phone-number prompts during auth bootstrap.
- `TELEGRAM_PASSWORD` may be stored alongside API credentials when Telegram two-step verification is enabled.
- Do not print full raw message dumps into logs unless explicitly required for debugging.
- Keep secrets in environment variables or local ignored files only.

## Summarization Priorities

- Prefer concise, high-value reporting over exhaustive recap.
- Surface the most important developments, risks, decisions, requests, deadlines, useful links, and notable context from the prepared data.
- Preserve concrete details when they materially improve accuracy or usefulness.
- When several messages describe the same situation, collapse them into one concise signal.
- When messages conflict or evidence is weak, keep the main report conservative and move uncertain details into uncertainties.

## Expected Repository Areas

- `scripts/`: runnable entrypoints for auth, collection, preparation, finalization, manual report delivery, and maintenance
- `src/`: reusable Python package code
- `docs/`: implementation and operations documents
- `data/`: local runtime data such as SQLite databases, report outputs, and session files
- `logs/`: local execution logs

## Commands

Environment setup:

- `python3.12 -m venv .venv && source .venv/bin/activate`
- `pip install -e '.[telegram,dev]'`

Test commands:

- `PYTHONPATH=src python3.12 -m unittest discover -s tests -v`

Lint and format commands:

- `python3.12 -m ruff check src scripts tests`
- `python3.12 -m ruff format src scripts tests`

Standard local run flow:

- `python3.12 scripts/auth_telegram.py`
- `python3.12 scripts/collect_messages.py --target <target> --lookback-hours 24 --max-messages 500`
- `python3.12 scripts/collect_messages.py --target <target> --collection-strategy lookback-only --lookback-hours 24 --max-messages 500`
- `python3.12 scripts/prepare_report_context.py --run-id <run_id>`
- Agent writes the final report and stores it with `python3.12 scripts/store_report.py --run-id <run_id> --input-path <report.md>`
- `python3.12 scripts/finalize_run.py --run-id <run_id> --mark-read --purge-raw`
- `python3.12 scripts/send_markdown_report.py --input-path <report.md> --target <target>`

Multi-target digest helpers:

- `python3.12 scripts/collect_digest_context.py --targets-config .secrets/daily_digest_targets.json`
- `python3.12 scripts/build_consolidated_digest.py --manifest-path <manifest.json>`

The lower-level scripts `prepare_summary_input.py` and `build_report_prompt.py` remain available for debugging or partial reruns.
Use `python3.12 scripts/migrate_report_layout.py` when older flat files in `data/reports/` need to be normalized into the dated folder layout.

Minimum pre-merge validation:

- Run `PYTHONPATH=src python3.12 -m unittest discover -s tests -v`
- Run `python3.12 -m compileall src scripts tests`
- Run `python3.12 -m ruff check src scripts tests`

## Agent Guidance

- For planning work, update documentation first.
- For implementation work, add or update tests for the behavior you change.
- When you change project structure or operating conventions, update both `PROJECT_OVERVIEW.md` and `AGENTS.md`.
- If a task concerns Telegram semantics, storage contracts, or cleanup behavior, check the specification before making assumptions.
- Alias mapping currently lives in `report_targets.target_key`. Existing rows take precedence over username parsing during target resolution.
- For forum targets, preserve topic metadata in `run_forum_topics` and keep forum message rows annotated with topic IDs and topic root message IDs.
- When preparing or reviewing report output, rely on the prepared bundle and let the model determine what matters.
- When writing a final report, use the generated report prompt/brief before falling back to the full bundle.
- For scheduled daily digests, prefer `lookback-only` collection so each run covers a deterministic time window instead of unread state.
- When delivering a report to Telegram, use the dedicated delivery script and keep it opt-in; never wire it into the standard collection/store/finalize pipeline without explicit user approval.

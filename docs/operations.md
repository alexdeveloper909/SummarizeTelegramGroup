# Operations

## Normal Runbook

1. Authenticate once with `python3 scripts/auth_telegram.py`.
2. Collect messages with `python3 scripts/collect_messages.py --target <target> --lookback-hours 24 --max-messages 500`.
3. Prepare the bundle with `python3 scripts/prepare_summary_input.py --run-id <run_id> --format both --output data/reports/<run_id>.summary`.
4. Generate the final report with an agent and persist it using `python3 scripts/store_report.py --run-id <run_id> --input-path <report.md>`.
5. Finalize with `python3 scripts/finalize_run.py --run-id <run_id> --mark-read --purge-raw`.

## Retry Paths

### Collection failure

- Inspect `collection_runs.error_summary`.
- Fix credentials, target resolution, or connectivity.
- Re-run collection.
- Do not purge raw rows manually unless you are intentionally discarding the failed run.

### Summarization failure

- Leave `raw_messages` intact.
- Re-run `prepare_summary_input.py` for the same `run_id`.
- Store the report only after the new summary is acceptable.

### Finalization failure

- Confirm `generated_reports` contains the report.
- Re-run `scripts/finalize_run.py`.
- If mark-as-read succeeded before the failure, the retry remains safe because `read_marked_at` is tracked.

## Cleanup

- Routine cleanup: `python3 scripts/purge_old_runs.py --older-than-hours 168`
- This script only removes raw rows for runs already marked `finalized`.
- Failed runs are preserved for debugging and must be reviewed deliberately.

## Automation Recipes

### Codex

```text
1. Run collect_messages.py for the configured target.
2. Capture the returned run_id.
3. Run prepare_summary_input.py for that run_id.
4. Summarize the bundle into Markdown using docs/prompts.md.
5. Store the report with store_report.py.
6. Run finalize_run.py with --mark-read --purge-raw.
```

### Claude Code

```text
1. Invoke collect_messages.py with explicit target and lookback arguments.
2. Feed the prepared Markdown or JSON bundle into the summarization prompt.
3. Persist the report with store_report.py.
4. Finalize only after the report write succeeds.
```

## Pre-Merge Validation

- `PYTHONPATH=src python3 -m unittest discover -s tests -v`
- `python3 -m compileall src scripts tests`
- `python3 -m ruff check src scripts tests`

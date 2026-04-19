# OpenClaw Daily Digest Cron Runbook

Goal: produce and publish the daily Telegram digest using the full consolidated report, without any extra shortening pass.

## Inputs

- Targets config: `.secrets/daily_digest_targets.json`
- Telegram credentials: `.secrets/telegram.env`
- Delivery target comes from the targets config
- Default lookback for cron: `24` hours

## Workflow

1. Run collection and context preparation:

```bash
python3 scripts/collect_digest_context.py --targets-config .secrets/daily_digest_targets.json --lookback-hours 24
```

2. Read the returned manifest JSON path.

3. For each manifest target with `status == "prepared"`:
   - read its `report_prompt_path`
   - read its `summary_markdown_path`
   - write a Ukrainian Markdown draft to `data/reports/DD.MM.YYYY/draft/<RUN_ID>.draft.md`
   - if the source bundle is sparse or empty, say so plainly instead of inventing significance

4. After drafts are written:
   - store each draft with `scripts/store_report.py`
   - finalize each stored run with `scripts/finalize_run.py --mark-read --purge-raw`
   - if one run fails, continue with the others

5. Build the consolidated digest from the manifest:

```bash
python3 scripts/build_consolidated_digest.py --manifest-path <MANIFEST_PATH>
```

6. Send the full consolidated report, not the shortened publish variant:

```bash
python3 scripts/send_markdown_report.py --input-path <CONSOLIDATED_REPORT_PATH> --target <DELIVERY_TARGET>
```

## Reporting guidance

- Filter noise and keep high-value information
- Preserve concrete links, offers, requests, deadlines, contacts, useful recommendations, and notable repeated topics
- Write in Ukrainian
- Prefer concise but information-dense reports
- Do not invent facts
- Partial success is acceptable, missing groups should not block publishing the rest

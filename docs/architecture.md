# Architecture

## Runtime Flow

```mermaid
flowchart TD
    A["auth_telegram.py"] --> B["collect_messages.py"]

    subgraph Telegram
        T1["Source chat / channel / forum"]
        T2["Optional delivery target"]
    end

    subgraph Pipeline["Default Summarization Pipeline"]
        C["SQLite staging: report_targets, collection_runs, raw_messages, run_forum_topics"]
        D["prepare_report_context.py"]
        E["Artifacts: summary JSON, summary Markdown, report prompt"]
        F["Agent report writing step"]
        G["store_report.py"]
        H["Stored report: generated_reports + report/*.report.md"]
        I["finalize_run.py"]
        J["Successful finalization: mark read + purge raw_messages"]
    end

    subgraph MultiTarget["Multi-target Digest Helpers"]
        M["collect_digest_context.py"]
        N["digest manifest + prepared per-target context"]
        O["Per-target agent reports"]
        P["build_consolidated_digest.py"]
        Q["full consolidated digest + publish brief"]
    end

    T1 --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    H --> I
    I --> J
    J --> T1
    M --> N
    N --> O
    O --> P
    P --> Q

    K["send_markdown_report.py"] --> T2
    H -. "explicit opt-in" .-> K
    Q -. "explicit opt-in" .-> K
```

## Component Boundaries

- `scripts/auth_telegram.py`: one-time interactive Telethon login bootstrap.
- `scripts/collect_messages.py`: resolves one target, fetches unread-first with a lookback fallback, stages normalized rows, records run status, and snapshots forum-topic metadata for forum runs.
- `scripts/collect_digest_context.py`: reads a JSON target list, logs into Telegram once, then sequentially collects and prepares per-target context for a multi-target digest while preserving partial failures.
- `scripts/prepare_report_context.py`: preferred orchestration step that writes both the summary bundle and report-writing brief under the dated report artifact tree.
- `scripts/prepare_summary_input.py`: builds an agent-friendly Markdown or JSON bundle from SQLite only.
- `scripts/build_report_prompt.py`: converts the prepared bundle into a generic report-writing brief for the agent.
- `scripts/store_report.py`: persists the agent-produced report to disk and to `generated_reports`, then updates the run with the stored report path.
- `scripts/finalize_run.py`: refuses to finalize until a stored report exists, then marks the source target as read if requested and purges raw rows by `run_id`.
- `scripts/purge_old_runs.py`: maintenance cleanup for old finalized runs.
- `scripts/send_markdown_report.py`: separate manual delivery path for an already-written report; it does not change collection-run state.
- `scripts/build_consolidated_digest.py`: reads a digest manifest, pulls stored per-target reports, writes one full consolidated document, and writes a separate publish-editing brief.

## Storage Model

- `report_targets`: stable target aliases and resolved Telegram metadata.
- `collection_runs`: per-invocation lifecycle state, message counts, error summaries, and finalization timestamps.
- `raw_messages`: temporary normalized staging rows scoped by `run_id`.
- `run_forum_topics`: per-run forum topic snapshot used to preserve topic-aware preparation and topic-scoped read acknowledgement.
- `generated_reports`: stored final Markdown reports for successful or in-progress finalization flows.
- `data/reports/DD.MM.YYYY/{summary,report_prompt,draft,report,final}`: on-disk artifact tree for one day's prepared bundles, prompts, drafts, canonical stored reports, and manually promoted finals.

## Target Resolution Rules

Resolution order:

1. Existing `report_targets.target_key`
2. Numeric Telegram entity ID
3. Username with or without `@`
4. Fallback alias key

This makes alias mapping explicit while still allowing direct one-off target references.

## Concurrency Notes

- SQLite runs in WAL mode with a busy timeout.
- Every raw row and cleanup action is scoped by `run_id`.
- Shared Telethon session files can still be a concurrency bottleneck. Prefer one session file per worker or serialized Telegram access if multiple automations share an account.
- For daily multi-target digests, prefer serialized Telegram collection with one shared session and parallelize only the summarization stage if needed.

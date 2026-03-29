# Telegram Group Summarizer Specification

Status: Draft  
Last updated: 2026-03-29

## 1. Purpose

Build a local, automation-friendly project that can:

1. Read Telegram messages from a configured group or channel.
2. Extract the important signals from unread content or, at most, the last 24 hours of content.
3. Produce a clear human-readable report.
4. Mark the processed Telegram messages as read after the run completes successfully.
5. Clean up staged raw message data after the report is produced.
6. Optionally post an already-written report Markdown file into a specified Telegram chat when an operator explicitly asks for delivery.

The expected operator is an AI agent running on a schedule, not a human manually running commands every morning.

## 2. Problem Statement

The user is a member of multiple Telegram groups and does not have time to read all activity manually. The system should turn noisy group traffic into a concise, useful report that highlights what actually matters.

## 3. Goals

- Support scheduled automation runs for one Telegram target per invocation.
- Collect messages with enough metadata to enable downstream summarization and report writing.
- Persist collected data locally in SQLite so the summarization stage does not depend on a live Telegram connection.
- Allow multiple automation runs for different targets at the same time.
- Produce a final report that can be read quickly during a morning review.
- Provide strong project documentation for both humans and coding agents.

## 4. Non-Goals

- Building a web UI in the first version.
- Automated message sending, replying, or moderation actions.
- Long-term archival of all Telegram history.
- Multi-user access control inside this repository.
- Real-time streaming or always-on background consumption.

## 5. Key Assumptions

- One automation run handles exactly one Telegram target.
- The automation provides a stable target identifier such as Telegram chat ID, channel ID, username, or alias resolved by configuration.
- The summarization model is provided by the agent environment and is not hard-coded into the collector script.
- A failed run must not delete raw data that may be needed for retry or debugging.
- Raw staged message data can be deleted after a successful report is produced and captured.
- Manual report delivery is a separate operator-invoked action and is not part of the default scheduled summarization pipeline.

## 6. External Constraints Verified Upfront

- Telethon supports iterating dialogs and messages and can address chats by numeric ID or username. Source: [Telethon quick start](https://docs.telethon.dev/en/stable/basic/quick-start.html)
- Telethon exposes read-acknowledgement methods for marking chat messages as read. Source: [Telethon client reference](https://docs.telethon.dev/en/stable/quick-references/client-reference.html)
- Telethon session storage can be backed by SQLite session files, and those session files are sensitive credentials that must never be committed. Source: [Telethon sessions](https://docs.telethon.dev/en/v2/modules/sessions.html)
- `AGENTS.md` is a plain Markdown root-level convention meant to guide coding agents with project-specific instructions. Source: [agents.md](https://agents.md/)

## 7. Primary Use Case

Daily automation run:

1. Agent starts in this repository with a target identifier supplied by automation parameters.
2. Collector script authenticates to Telegram through Telethon.
3. Collector fetches unread messages for the target. If unread state is unavailable or unsuitable, it fetches messages from the last 24 hours, bounded by configurable limits.
4. Collector writes normalized message records into SQLite, grouped by a unique run ID and target ID.
5. A preparation script reads the staged records and produces an agent-friendly bundle for summarization.
6. The agent performs summarization, optionally using web search for deeper investigation when needed.
7. The agent outputs a report in Markdown or another agreed format.
8. On successful completion, the pipeline marks the target as read in Telegram and purges staged raw rows for that run.
9. If a human or agent explicitly requests delivery, a separate script can post the already-written report Markdown into a specified Telegram chat without changing run-finalization behavior.

## 8. Functional Requirements

### 8.1 Message Collection

- The system must collect messages for one configured Telegram target per run.
- The system must support both unread-message mode and lookback-window mode.
- The effective fetch scope must never exceed the configured maximum lookback window, defaulting to 24 hours.
- The collector must capture enough metadata for downstream summarization, including:
  - Telegram target ID
  - Message ID
  - Message timestamp
  - Sender ID and sender display name when available
  - Message text or caption
  - Reply-to message ID when present
  - Forwarded/source markers when present
  - Link presence
  - Media presence and media type summary when detectable
  - Edit timestamp when present
  - Service-message flag

### 8.2 Storage

- The system must persist raw collected messages in local SQLite.
- The schema must support concurrent runs for different Telegram targets.
- Each row must be associated with both a target identifier and a run identifier.
- The system should keep enough run metadata to debug failures and confirm completion state.

### 8.3 Summarization

- The system must expose a local script or agent-friendly data package that lets an AI agent summarize collected messages without calling Telegram again.
- The summarization stage must produce:
  - A short executive summary
  - A list of high-signal events or topics
  - Important links or resources mentioned
  - Action items, requests, or decisions if detectable
  - Notable disagreements, announcements, deadlines, or risks if present
- The summarization stage may use web research when a topic needs verification or context expansion.

### 8.4 Completion Behavior

- After the report is successfully produced, the run must mark the Telegram target as read.
- After successful report generation and delivery, staged raw message rows for that run must be deleted.
- If the run fails before the report is finalized, raw rows must remain available for retry and debugging.

### 8.5 On-Demand Report Delivery

- The system may provide a separate script that reads an existing Markdown report from disk and sends it to a specified Telegram chat.
- This script must be explicitly invoked by an operator or agent and must not run automatically as part of collection, preparation, report storage, or finalization.
- Delivery must reuse the local Telethon session model already used by the rest of the project.
- Delivery must convert Markdown into Telegram-ready formatting through `telegramify-markdown`.
- Delivery must split oversized outbound content into multiple Telegram messages so each message stays within Telegram's documented text-length limits.
- Delivery must not mark source chats as read, purge staged raw rows, or otherwise alter summarization-run state.

### 8.6 Documentation

- The repository must contain a human-oriented setup guide.
- The repository must contain a root `AGENTS.md` file that explains the project, available scripts, operating conventions, and safety rules for coding agents.
- The repository must maintain a root documentation entry point that links to deeper docs under `docs/`.

## 9. Non-Functional Requirements

### 9.1 Reliability

- Re-running the same failed run should not create uncontrolled duplication.
- The collector should handle empty result sets cleanly.
- Network or Telegram API failures should be surfaced with actionable logs.

### 9.2 Concurrency

- Multiple automation jobs may run at the same time for different Telegram targets.
- SQLite must be configured for concurrent access patterns as far as practical, including WAL mode and a busy timeout.
- The design must avoid ambiguous global cleanup logic. Cleanup must be scoped by run ID.

### 9.3 Security and Privacy

- Telegram credentials and session files must remain local and uncommitted.
- Raw message retention should be minimal.
- Logs must avoid dumping sensitive raw content unnecessarily.

### 9.4 Operability

- Local scripts must be runnable by an agent without interactive editing of source code.
- The system should use explicit CLI arguments or environment variables, not hidden constants.
- Each run should emit enough structured logs to diagnose which target, run ID, and phase failed.
- The manual report-delivery path may depend on Python 3.10 or newer because `telegramify-markdown`'s entity-based API requires it.

## 10. Architectural Proposal

### 10.1 Components

1. `collector`: Python script using Telethon to fetch messages and store normalized rows in SQLite.
2. `storage`: SQLite database plus schema/migration helpers.
3. `prepare_summary_input`: Python script that reads a run from SQLite and emits an agent-friendly Markdown or JSON package.
4. `summarizer`: agent-driven step that reads prepared input, extracts signals, optionally browses the web, and writes a report.
5. `finalize_run`: Python script that marks the Telegram target as read and purges staged raw rows for the successful run.
6. `report_delivery`: Python script and helper code that optionally send an already-written Markdown report into a specified Telegram chat.
7. `docs`: human and agent documentation.

### 10.2 Separation of Concerns

- Telegram access belongs only in collection, finalization, and the explicitly invoked report-delivery script.
- The summarization stage should work entirely from the SQLite-backed prepared dataset.
- Cleanup should happen only after successful report creation.
- Report delivery should remain isolated from collection and finalization state transitions so it can be invoked on demand without changing pipeline behavior.

This separation keeps Telegram access narrow, makes summarization reproducible, and reduces accidental data loss.

## 11. Proposed Repository Structure

```text
.
├── AGENTS.md
├── PROJECT_OVERVIEW.md
├── README.md
├── user_guide.md
├── data/
│   ├── reports/
│   │   └── DD.MM.YYYY/
│   │       ├── draft/
│   │       ├── final/
│   │       ├── report/
│   │       ├── report_prompt/
│   │       └── summary/
│   ├── sqlite/
│   └── sessions/
├── docs/
│   ├── specification.md
│   ├── architecture.md
│   ├── operations.md
│   └── prompts.md
├── logs/
├── scripts/
│   ├── auth_telegram.py
│   ├── collect_messages.py
│   ├── prepare_report_context.py
│   ├── prepare_summary_input.py
│   ├── build_report_prompt.py
│   ├── send_markdown_report.py
│   ├── finalize_run.py
│   └── purge_old_runs.py
├── src/
│   └── telegram_group_summarizer/
│       ├── config.py
│       ├── db.py
│       ├── models.py
│       ├── telethon_client.py
│       ├── collection.py
│       ├── report_context.py
│       ├── report_prompt.py
│       ├── report_delivery.py
│       ├── summary_input.py
│       ├── finalization.py
│       └── logging_utils.py
└── tests/
    ├── test_db.py
    ├── test_collection_normalization.py
    ├── test_report_context.py
    ├── test_report_prompt.py
    ├── test_prepare_summary_input.py
    └── test_finalization.py
```

The exact layout can change, but the boundary between scripts, library code, docs, and data should remain explicit.
Within `data/reports/`, generated artifacts should be grouped by run date using `DD.MM.YYYY` directories so operators can browse one day's outputs at a time, while per-artifact subfolders keep summaries, prompts, drafts, stored reports, and promoted finals distinct.

## 12. Data Model Proposal

### 12.1 Tables

### `report_targets`

Purpose: stable configuration reference for a Telegram target.

Suggested fields:

- `id` primary key
- `target_key` unique human-stable key used by automation
- `telegram_entity_id` numeric Telegram entity ID when known
- `telegram_entity_type` such as `group`, `supergroup`, or `channel`
- `display_name`
- `is_active`
- `created_at`
- `updated_at`

### `collection_runs`

Purpose: track each automation invocation.

Suggested fields:

- `id` primary key
- `run_id` unique string generated per invocation
- `target_id` foreign key to `report_targets`
- `started_at`
- `completed_at`
- `status` enum-like text such as `started`, `collected`, `summarized`, `finalized`, `failed`
- `mode` such as `unread` or `lookback`
- `lookback_hours`
- `message_count`
- `error_summary`

### `raw_messages`

Purpose: temporary normalized message staging area for one run.

Suggested fields:

- `id` primary key
- `run_id` foreign key-like reference to `collection_runs.run_id`
- `target_id` foreign key to `report_targets`
- `telegram_message_id`
- `message_timestamp`
- `sender_id`
- `sender_name`
- `text_content`
- `reply_to_message_id`
- `forward_source`
- `has_links`
- `has_media`
- `media_kind`
- `edited_at`
- `is_service_message`
- `raw_json` optional serialized normalized payload
- `created_at`

Suggested constraints and indexes:

- unique index on `(run_id, telegram_message_id)`
- index on `(target_id, message_timestamp)`
- index on `(run_id)`

### `generated_reports`

Purpose: optional audit trail for successful summaries.

Suggested fields:

- `id` primary key
- `run_id` unique
- `target_id`
- `report_markdown`
- `created_at`

This table is optional for version one. If privacy requirements are strict, the final report may instead be written to a file or automation output only.

### 12.2 Database Behavior

- Enable SQLite WAL mode.
- Set a busy timeout.
- Scope inserts, reads, and cleanup by `run_id`.
- Prefer migrations from the start, even if version one has only one migration.

## 13. Telegram Integration Proposal

### 13.1 Authentication

- Use Telethon API ID and API hash from environment variables.
- Use a local session file stored under `data/sessions/` or a secrets directory.
- Never commit session files.
- Provide a one-time `auth_telegram.py` bootstrap script for interactive login.

### 13.2 Target Resolution

Support one of:

- direct numeric Telegram entity ID
- username
- configured alias mapped in SQLite or config file

The collector should resolve the target once and log what entity it actually used.

### 13.3 Fetch Strategy

Preferred order:

1. Collect unread messages when that state is trustworthy and available.
2. If unread count is zero or unread boundaries are unclear, collect messages newer than `now - lookback_hours`.
3. Apply a hard upper bound such as `--max-messages` to avoid pathological runs.

### 13.4 Mark-As-Read Strategy

- Mark the target as read only after report generation succeeds.
- If report generation fails, do not mark as read.
- Finalization should be idempotent so repeated success handling does not break later retries.

## 14. Summarization Contract

The summarization stage should consume prepared input, not raw Telegram API objects.

Prepared input should include:

- run metadata
- target metadata
- chronologically ordered normalized messages
- extracted candidate URLs
- basic sender statistics
- optional reply-thread groupings

The report format should include:

1. Headline summary
2. Why this matters
3. Key topics and signals
4. Important links
5. Action items or follow-ups

## 15. Automation Contract

Each scheduled automation should be able to pass:

- target key or Telegram entity identifier
- lookback hours, default `24`
- max messages limit
- output path or output mode
- run ID, if orchestration wants to provide one

Recommended CLI shape:

```bash
python scripts/collect_messages.py --target team_alpha --lookback-hours 24 --max-messages 500
python scripts/prepare_report_context.py --run-id <RUN_ID>
python scripts/finalize_run.py --run-id <RUN_ID> --mark-read --purge-raw
```

The exact commands can change later, but the automation interface should remain parameterized and explicit.

## 16. Logging and Observability

Each run should log:

- run ID
- target key
- resolved Telegram entity
- fetch mode
- fetched message count
- summarization input path or record count
- report output location
- finalization result

Structured JSON logs are preferable, but readable plain logs are acceptable for version one.

## 17. Failure Handling

### 17.1 Collection Failure

- Mark run as `failed`
- Keep already staged rows
- Do not mark Telegram target as read
- Emit actionable error details

### 17.2 Summarization Failure

- Keep staged rows
- Do not mark Telegram target as read
- Preserve enough intermediate state for retry

### 17.3 Finalization Failure

- Report summary may already exist
- Run should be marked as partially completed or failed-finalization
- Retry path must allow reattempting mark-as-read and purge safely

## 18. Security Requirements

- Add `.gitignore` rules for session files, SQLite files, logs, and generated reports if those contain sensitive content.
- Prefer environment variables for secrets.
- Document exactly which variables are required.
- Avoid storing raw media binaries in version one unless there is a strong need.

## 19. Documentation Requirements

At minimum the repository documentation set should include:

- `PROJECT_OVERVIEW.md`: index and document map
- `docs/specification.md`: this file
- `user_guide.md`: setup, auth, env vars, execution, and troubleshooting
- `AGENTS.md`: agent-facing guidance
- `docs/prompts.md`: suggested summarization/report prompts for agents
- `docs/operations.md`: runbook for retries, cleanup, and routine maintenance

## 20. Risks and Design Notes

### 20.1 Shared Telethon Session Risk

Multiple concurrent jobs using the same Telethon session file may create locking or state issues because Telethon supports SQLite-backed session storage. This is an engineering inference from the storage model and the planned concurrent-job requirement. The implementation should either:

- allocate separate session files per automation worker or target, or
- enforce serialized Telegram access when sharing one session

This needs explicit handling in version one.

### 20.2 SQLite Concurrency Limits

SQLite is acceptable for this scale, but write contention still exists. Keep transactions short and cleanup narrowly scoped by run ID.

### 20.3 Privacy Tradeoff

Keeping only temporary raw message staging is privacy-friendly, but it reduces debuggability. The design should keep failed-run data until resolved, then purge it deliberately.

## 21. Open Questions

- Should one Telegram account serve all targets, or should different targets use different accounts/sessions?
- Should generated reports be persisted locally, or only emitted as automation output?
- Is media content itself required later, or is metadata about media sufficient for version one?
- Should alias-to-target mapping live in SQLite, a YAML file, or pure CLI parameters?
- What is the preferred report destination: stdout, Markdown file, inbox item, or all three?

## 22. Implementation Checklist

Use this as the execution checklist. Tasks are intentionally granular so they can be marked done incrementally.

### Phase 1: Repository and Tooling Baseline

- [x] Add Python project metadata and dependency management
- [x] Add `.gitignore` rules for sessions, SQLite data, logs, reports, and local secrets
- [x] Create `src/`, `scripts/`, `tests/`, and `docs/` structure
- [x] Add logging configuration utilities
- [x] Add configuration loader for environment variables and CLI defaults

### Phase 2: Database Foundation

- [x] Choose migration tool or lightweight migration approach
- [x] Implement initial SQLite schema for `report_targets`, `collection_runs`, and `raw_messages`
- [x] Decide whether `generated_reports` is in or out for version one
- [x] Enable WAL mode and busy timeout on database initialization
- [x] Add tests for schema creation and unique constraints

### Phase 3: Telegram Authentication and Target Resolution

- [x] Implement one-time Telethon authentication bootstrap script
- [x] Document required Telegram API credentials in `user_guide.md`
- [x] Implement target resolution by numeric ID and username
- [x] Add optional alias mapping design
- [x] Add tests for target parsing and configuration validation

### Phase 4: Message Collection

- [x] Implement collector entrypoint with `--target`, `--lookback-hours`, and `--max-messages`
- [x] Create a unique `run_id` per invocation
- [x] Implement unread-first fetch logic
- [x] Implement lookback-window fallback capped at 24 hours by default
- [x] Normalize Telegram messages into the SQLite schema
- [x] Record run status transitions and message counts
- [x] Add tests for normalization of text, replies, links, and service messages

### Phase 5: Summary Input Preparation

- [x] Implement script to read one run from SQLite and build an agent-friendly summary bundle
- [x] Include sender stats, URLs, and chronological ordering
- [x] Decide on Markdown, JSON, or dual output for the prepared bundle
- [x] Add tests for bundle generation and empty-run behavior

### Phase 6: Agent Summarization Workflow

- [x] Define report template and section ordering
- [x] Write `docs/prompts.md` with agent prompt guidance
- [x] Define when web research is appropriate during summarization
- [x] Decide how automation captures the final report output
- [x] Add an example end-to-end dry run for one target

### Phase 7: Finalization and Cleanup

- [x] Implement finalization script for successful runs
- [x] Mark target as read only after report success
- [x] Purge raw rows by `run_id`
- [x] Handle retry-safe finalization semantics
- [x] Add tests for finalization and cleanup behavior

### Phase 8: Documentation and Operations

- [x] Complete `user_guide.md` with setup, auth, configuration, and troubleshooting
- [x] Expand `AGENTS.md` with concrete commands once scripts exist
- [x] Add `docs/operations.md` for retries, cleanup, and maintenance
- [x] Add `docs/architecture.md` with implementation-level diagrams if needed
- [x] Add sample automation recipes for Codex, Claude Code, or similar agent runners

### Phase 9: Quality Gates

- [x] Add unit tests for database, collection, preparation, and finalization
- [x] Add one small integration test around a mocked collector flow
- [x] Define linting and formatting commands
- [x] Document the minimum pre-merge validation steps

## 23. Minimum Viable Version Definition

Version one is complete when:

- A configured Telegram target can be fetched by automation.
- New messages from unread state or the last 24 hours are written to SQLite.
- An agent can read prepared input and generate a useful report.
- Successful runs mark the target as read.
- Successful runs purge staged raw rows for that run.
- A human can set up the project using the documentation alone.

## 24. Suggested First Implementation Slice

Build in this order:

1. project scaffolding and config loading
2. SQLite schema and migration setup
3. Telegram auth bootstrap
4. collector for one target and one run
5. summary-input preparation
6. manual agent summarization flow
7. finalization and cleanup

That sequence reduces risk by validating Telegram access and storage before spending time on report polish.

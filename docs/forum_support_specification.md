# Telegram Forum Support Specification

Status: Implemented
Last updated: 2026-03-29

## 1. Purpose

Define how this project should support summarizing a Telegram forum, meaning a Telegram supergroup with topics enabled, as one coherent report for the whole forum.

The design must keep the current pipeline shape:

1. collect Telegram data locally
2. store normalized rows in SQLite
3. prepare an agent-friendly bundle
4. let the agent write one report
5. only then mark the covered content as read and purge staged raw data

The design must not treat each topic as a separate end-user report.

## 2. Problem Statement

The current collector and summary bundle assume one flat chat history for one target. That model is acceptable for a normal group or channel, but it is a poor fit for a forum:

- a single forum may contain many active topics in the same 24-hour window
- a flat message dump interleaves unrelated topics and becomes noisy
- a per-topic report would create too much output and does not match the desired user experience
- current finalization marks the whole target as read, which is too coarse if only some topics were actually covered

The desired behavior is one intelligent forum-wide summary that covers the important activity across topics without turning into a 20-topic laundry list.

## 3. Goals

- Support one forum target per run using the same high-level collection, preparation, report, and finalization flow already used for standard Telegram targets.
- Produce one report for the entire forum, not one report per topic.
- Cover active topics within the configured lookback window, defaulting to 24 hours.
- Preserve topic boundaries in storage and prepared bundles so the summarizer can reason across topics cleanly.
- Keep the output selective and high-signal by ranking and collapsing low-value topic activity.
- Use Telethon primitives that match forum semantics instead of relying on flat-history assumptions.
- Keep read-state handling conservative and topic-aware.

## 4. Non-Goals

- Reusing the current summarization flow by pretending every topic is an independent chat and then concatenating many separate reports.
- Emitting one section per topic regardless of importance.
- Marking the entire forum as read when only a subset of topics was collected.
- Introducing automatic report delivery into the default forum summarization flow.
- Building topic-specific moderation, reply, or posting features.

## 5. Verified Telethon Findings

The following forum-related primitives are available and were verified against the repository's local Telethon package version `1.42.0` and official Telethon TL documentation:

- Forum-enabled channels expose a `forum` flag on `Channel`.
- Telethon exposes `functions.messages.GetForumTopicsRequest` for enumerating forum topics.
- `ForumTopic` includes `id`, `title`, `top_message`, `date`, `unread_count`, `unread_mentions_count`, `unread_reactions_count`, and pinned/closed/hidden flags.
- Telethon exposes `functions.messages.GetRepliesRequest`, which can fetch the message thread rooted at a topic's `top_message`.
- Message reply metadata includes forum-specific fields through `MessageReplyHeader.forum_topic` and `MessageReplyHeader.reply_to_top_id`.
- Telethon exposes `functions.messages.ReadDiscussionRequest(peer, msg_id, read_max_id)`, which allows topic-thread read acknowledgement.
- Telethon's high-level `send_read_acknowledge` remains chat-scoped and maps to `channels.ReadHistoryRequest` or `messages.ReadHistoryRequest`, so it is not precise enough for forum v1 finalization.

These findings are enough to design a topic-aware collector and a topic-aware finalizer without inventing custom Telegram semantics.

## 6. Product Behavior

### 6.1 Target Mode

The collector should support:

- `auto`: default; detect whether the resolved target is a forum
- `chat`: force existing flat-chat behavior
- `forum`: force forum behavior and fail clearly if the target is not forum-enabled

This allows the operator or automation to say "this target is a Telegram forum" while still supporting auto-detection.

### 6.2 Run Contract

One run still handles exactly one Telegram target.

For forum targets, that one run should:

1. resolve the forum target
2. enumerate forum topics
3. select the topics relevant to the configured window
4. collect topic-thread messages
5. prepare one forum-aware bundle
6. produce one final report for the whole forum
7. mark only the covered topic threads as read

## 7. Collection Design

### 7.1 Why Forum Collection Must Differ

A forum is not just a normal group with more messages. The collector needs topic-aware steps because topic title, unread counters, thread roots, and topic-level read state are first-class data.

A flat `iter_messages(peer)` pass is insufficient as the primary strategy because:

- it loses topic structure in the prepared bundle
- it makes cross-topic summarization much noisier
- it does not naturally support topic-scoped finalization
- it prevents reliable coverage accounting per topic

### 7.2 Topic Catalog Snapshot

For forum runs, collection should start by paging through `GetForumTopicsRequest` and storing a per-run topic catalog snapshot.

Each snapshot row should include at minimum:

- `run_id`
- `target_id`
- `forum_topic_id`
- `forum_topic_title`
- `forum_topic_top_message_id`
- `forum_topic_date`
- `unread_count`
- `unread_mentions_count`
- `unread_reactions_count`
- `is_pinned`
- `is_closed`
- `is_hidden`

This snapshot is needed even if a topic later contributes few or zero collected messages, because it gives the summarizer and finalizer the forum structure for the run.

### 7.3 Topic Selection

The collector should define an "active topic" as a topic that satisfies at least one of:

- the topic's last activity timestamp is within the effective lookback window
- the topic's unread count is greater than zero
- the operator explicitly requested forum mode and the topic is pinned with recent activity

The prepared forum report should only reason over active topics, not the entire lifetime topic catalog.

### 7.4 Message Fetch Strategy

The collector should fetch per-topic thread messages using `GetRepliesRequest` rooted at `ForumTopic.top_message`.

Recommended strategy:

1. Enumerate all active topics.
2. Rank topics by a generic priority signal:
   - unread count
   - recency
   - pinned status
   - previous pass message volume
3. Run a first coverage pass that fetches a small capped slice for every active topic.
4. Spend the remaining global message budget on the highest-priority topics.

This two-pass strategy matters because a forum with 20 active topics should not let one noisy thread consume the entire run budget.

### 7.5 Message Normalization

Raw message storage should remain in the existing `raw_messages` flow, but forum-aware fields need to be added.

Each raw message row collected from a forum should carry:

- `forum_topic_id`
- `forum_topic_top_message_id`
- `reply_to_top_message_id`
- `is_forum_topic_message`

The collector should also preserve the existing generic message fields such as sender, timestamp, text, reply target, links, media, and service-message flag.

When messages are fetched through a known topic thread, the topic assignment should come from the fetch context first, with reply-header fields stored as additional evidence.

### 7.6 Service Messages

Forum-specific service messages such as topic creation, rename, close, reopen, or pin changes should be stored, but the prepared bundle should separate them from normal discussion messages.

They can matter for the report, but they should not dominate the main narrative.

## 8. Storage Changes

### 8.1 New Table

Add a per-run topic snapshot table, for example `run_forum_topics`.

Purpose:

- persist topic catalog metadata separately from raw messages
- support reporting on topic activity even when message counts are low
- support topic-scoped finalization using the topic root message

### 8.2 `raw_messages` Extensions

Extend `raw_messages` with nullable forum columns:

- `forum_topic_id`
- `forum_topic_top_message_id`
- `reply_to_top_message_id`
- `is_forum_topic_message`

These columns stay nullable so normal chats and channels continue to use the same table.

### 8.3 Run Metadata

Extend `collection_runs` with forum-aware fields such as:

- `target_mode`
- `forum_topic_count`
- `forum_active_topic_count`

This will make run logs and debugging much clearer.

## 9. Prepared Bundle Design

### 9.1 Core Requirement

Forum support must not reuse the existing "flat full chronology first" summary bundle as-is.

Instead, the prepared bundle should become topic-aware and intentionally compact.

### 9.2 Forum Bundle Shape

The bundle should include:

- `forum_overview`
  - forum display name
  - run metadata
  - total topics seen
  - active topics collected
  - total collected messages
- `topic_index`
  - one entry per active topic with counts and metadata
- `candidate_urls`
  - deduplicated across all topics
- `topic_groups`
  - grouped messages per topic
- `other_activity`
  - collapsed low-signal topics

### 9.3 Per-Topic Metrics

Each topic entry should include at minimum:

- topic title
- topic id
- top message id
- collected message count
- unique sender count
- last activity timestamp
- unread snapshot counts
- link count
- media count
- service message count

These are generic, non-domain heuristics that help the summarizer rank what deserves attention.

### 9.4 Excerpts Instead of Full Dumps

The Markdown bundle used by the agent should prefer:

- a forum overview
- a ranked topic radar
- compact per-topic excerpts for the most important topics
- a short "other activity" section for the rest

The JSON bundle may remain more complete, but the Markdown input should not dump every message from every topic unless the forum is very small.

### 9.5 Topic Collapsing Rules

Low-signal topics should be collapsed when they are low on message count, sender diversity, recency, and useful artifacts such as links or decisions.

The output should not force one subsection per topic. Topics are an organizing input, not a required one-to-one output format.

## 10. Report-Writing Contract

Forum reports should still be one report, but the prompt must become forum-aware.

The report should:

- open with the forum name
- summarize the most important developments across the whole forum first
- mention topic names only when they materially help the reader
- combine related topics when that improves clarity
- collapse minor topics into one short sentence or bullet
- keep uncertain or weakly evidenced details in an uncertainty section instead of overclaiming

Recommended report structure:

1. Headline summary
2. Cross-topic developments
3. Notable topic threads
4. Important links
5. Actions, requests, decisions, or deadlines
6. Uncertainties if needed

The current generic prompt can stay as the base, but forum mode should inject forum-specific reading order and compression rules.

## 11. Finalization and Read-State Rules

### 11.1 Safety Principle

Forum finalization must be topic-aware.

The project must not call chat-wide read acknowledgement for forum runs in v1.

### 11.2 Topic-Scoped Finalization

For each collected topic, finalization should store the highest collected message ID for that topic and then call:

- `messages.ReadDiscussionRequest(peer=<forum>, msg_id=<topic_top_message_id>, read_max_id=<highest_collected_message_id>)`

This acknowledges only the covered discussion thread.

### 11.3 Failure Behavior

If topic-scoped read acknowledgement fails for any collected topic:

- finalization should fail
- raw data should remain available
- the run should not be considered fully finalized

This is consistent with existing cleanup safety rules.

### 11.4 Mentions and Reactions

Forum v1 should not clear mentions or reactions globally.

If the project later wants topic-level clearing, it should do so only with the Telegram methods that accept `top_msg_id`.

## 12. CLI and Operator Experience

The main scripts should remain the same.

Recommended CLI changes:

- `scripts/collect_messages.py`
  - add `--target-mode {auto,chat,forum}`
  - optionally add forum-specific tuning flags such as:
    - `--forum-topic-limit`
    - `--forum-topic-probe-messages`
    - `--forum-max-messages-per-topic`

The default automation flow should stay:

1. collect
2. prepare report context
3. agent writes report
4. store report
5. finalize run

Forum support is an extension of the current flow, not a separate product.

## 13. Implementation Areas

The following repository areas are expected to change:

- `src/telegram_group_summarizer/models.py`
  - add forum-aware dataclasses or optional fields
- `src/telegram_group_summarizer/telethon_client.py`
  - add forum detection, topic enumeration, per-topic thread fetch, topic-scoped read acknowledgement
- `src/telegram_group_summarizer/collection.py`
  - add forum-mode collection orchestration and normalization
- `src/telegram_group_summarizer/db.py`
  - add schema helpers and new topic snapshot persistence
- `src/telegram_group_summarizer/summary_input.py`
  - build forum-aware prepared bundles
- `src/telegram_group_summarizer/report_prompt.py`
  - add forum-specific prompt guidance
- `src/telegram_group_summarizer/finalization.py`
  - finalize forum runs per topic
- `scripts/collect_messages.py`
  - surface target mode and forum tuning flags
- tests
  - add forum-specific unit and integration coverage

## 14. Validation Requirements

Minimum validation for forum support should include:

- unit tests for forum target detection
- unit tests for topic pagination
- unit tests for message normalization with topic metadata
- unit tests for topic ranking and collapsing
- unit tests for forum-aware report prompt generation
- unit tests for topic-scoped finalization
- integration-style tests with fake forum topics and topic-thread messages

Before enabling forum mode by default, perform one manual live validation against a real Telegram forum to confirm:

- topic enumeration order
- topic activity timestamps
- thread fetch behavior for both named topics and the general topic
- topic-scoped read acknowledgement behavior

## 15. Rollout Plan

### Phase 1: Telethon and Schema Support

- add forum-aware Telethon methods
- add schema migration for topic snapshots and forum message columns
- add collector support for `--target-mode forum`

### Phase 2: Forum Bundle and Prompt

- extend prepared summary bundle with topic-aware structure
- update Markdown and JSON outputs
- add forum-specific report prompt rules

### Phase 3: Finalization and Tests

- implement topic-scoped read acknowledgement
- add forum finalization tests
- run manual validation against a live forum

## 16. Open Questions

- Confirm live behavior for the forum's general topic and verify whether its thread root behaves the same as named topics for `GetRepliesRequest`.
- Decide whether low-value topic service events should appear in the main report or only in a side section.
- Decide whether `auto` mode should silently downgrade a forum target to flat chat mode or fail closed when topic APIs are unavailable. This specification recommends failing closed.

## 17. Source References

- Telethon TL: `GetForumTopicsRequest`  
  https://tl.telethon.dev/methods/messages/get_forum_topics.html
- Telethon TL: `ForumTopic`  
  https://tl.telethon.dev/constructors/forum_topic.html
- Telethon TL: `GetRepliesRequest`  
  https://tl.telethon.dev/methods/messages/get_replies.html
- Telethon TL: `MessageReplyHeader`  
  https://tl.telethon.dev/constructors/message_reply_header.html
- Telethon TL: `InputReplyToMessage`  
  https://tl.telethon.dev/constructors/input_reply_to_message.html
- Telethon TL: `ReadDiscussionRequest`  
  https://tl.telethon.dev/methods/messages/read_discussion.html

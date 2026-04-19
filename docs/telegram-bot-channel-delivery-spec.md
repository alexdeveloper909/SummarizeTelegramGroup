# Telegram bot channel delivery migration spec

Status: planned, not implemented
Last updated: 2026-04-19

## Goal

Change the daily digest publishing step so the final digest is posted to the Telegram channel by a **separate bot identity**, not by Alex's personal Telegram account.

Primary reason:

- posts sent by Alex's own account are treated as Alex's own activity
- those posts often appear already read on Alex's phone
- Telegram therefore does not send a push notification for the newly published digest

Using a bot identity should restore the normal subscriber experience: the channel receives a new post from the bot, and Alex's phone can notify him like any other channel subscriber.

## Current state

The current scheduled digest job ends with:

```bash
python3 scripts/send_markdown_report.py --input-path <CONSOLIDATED_REPORT_PATH> --target <DELIVERY_CHANNEL_ID>
```

Today that script:

- loads the normal Telegram user credentials from `.secrets/telegram.env`
- creates a Telethon client using the regular user session
- resolves the target chat
- sends the Markdown report in one or more chunks

Relevant files:

- `scripts/send_markdown_report.py`
- `src/telegram_group_summarizer/report_delivery.py`
- `src/telegram_group_summarizer/telethon_client.py`
- `src/telegram_group_summarizer/config.py`

Important boundary:

- **collection and finalization should keep using Alex's user account**
- **only outbound digest publishing should move to the bot**

That keeps read access and mark-read behavior unchanged.

## Recommendation

Implement the first version with a **Telegram bot token plus a dedicated outbound delivery client**, while keeping the rest of the pipeline unchanged.

Recommended technical shape:

- keep **Telethon for collection/finalization** with Alex's user session
- add a **separate delivery mode for bot publishing**
- prefer **Telethon bot login** for the first implementation to minimize code churn

Why this path:

- smallest change to the existing codebase
- existing message chunking and Telethon entity conversion can likely be reused
- still achieves the real product goal because the sender identity becomes the bot

A later cleanup could switch outbound delivery to the pure Bot API if desired, but that is not required for the notification fix.

## Expected result after migration

When the cron job publishes the digest:

- the message appears in the target channel as posted by the bot
- Alex remains a normal subscriber to that channel
- Alex's phone should receive the channel notification, assuming channel notifications are enabled on the phone and the channel is not muted
- the message should no longer be auto-read purely because Alex's own account posted it

## Non-goals

- changing message collection logic
- changing report generation logic
- changing mark-read logic for source groups/forums
- redesigning the whole digest pipeline
- solving Telegram client notification quirks unrelated to sender identity

## Preconditions

Before implementation day, these manual setup steps will be needed:

1. Create a bot with `@BotFather`
2. Save the bot token securely
3. Add the bot to the destination channel
4. Promote the bot to channel admin with permission to post messages
5. Confirm the bot can post in the target channel
6. Confirm Alex is subscribed to that same channel on the phone and notifications are enabled

## Proposed configuration changes

Add bot-specific outbound settings without breaking existing user-session behavior.

Suggested new env vars:

```bash
TELEGRAM_DELIVERY_MODE=user
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_SESSION_NAME=telegram_group_summarizer_bot
```

Behavior:

- `TELEGRAM_DELIVERY_MODE=user` keeps current behavior
- `TELEGRAM_DELIVERY_MODE=bot` uses the bot identity for `send_markdown_report.py`
- `TELEGRAM_BOT_TOKEN` is required when delivery mode is `bot`
- `TELEGRAM_BOT_SESSION_NAME` is optional if Telethon bot sessions are used

Suggested secret file:

- `.secrets/telegram_bot.env`

Alternative: keep everything in `.secrets/telegram.env`, but I prefer a separate file because it cleanly separates user and bot credentials.

## Proposed code changes

### 1. Extend config model

File:

- `src/telegram_group_summarizer/config.py`

Add fields like:

- `telegram_delivery_mode`
- `telegram_bot_token`
- `telegram_bot_session_name`

Add validation helpers such as:

- `validate_bot_delivery_credentials()`

Important:

- do **not** make bot token required globally
- only require it when the delivery path explicitly requests bot mode

## 2. Add a dedicated outbound client factory

File:

- `src/telegram_group_summarizer/telethon_client.py`

Add a helper conceptually like:

- `create_telethon_bot_client(config)`

Expected behavior:

- create a separate session path under `data/sessions/`
- authenticate with `bot_token`
- keep it isolated from the user session used for collection/finalization

## 3. Update the delivery entrypoint

File:

- `scripts/send_markdown_report.py`

Change it so it selects the sender based on config or an explicit CLI flag.

Preferred CLI shape:

```bash
python3 scripts/send_markdown_report.py --input-path <report.md> --target <target> --sender bot
```

Suggested behavior:

- `--sender user` means current behavior
- `--sender bot` means outbound bot identity
- if `--sender` is omitted, fall back to `TELEGRAM_DELIVERY_MODE`

This keeps manual testing simple and makes cron behavior explicit.

## 4. Keep report formatting and chunking unchanged

File:

- `src/telegram_group_summarizer/report_delivery.py`

The current logic already:

- reads Markdown from disk
- converts it into Telegram-safe entities
- splits long content into chunks
- sends chunks sequentially

That behavior should stay the same.

Needed verification:

- confirm the current Telethon entity types and send path work correctly under a bot-authenticated Telethon client
- if not, adapt only the outbound send layer, not the report building logic

## 5. Update cron job command

Current final step inside the daily digest automation:

```bash
python3 scripts/send_markdown_report.py --input-path <CONSOLIDATED_REPORT_PATH> --target <DELIVERY_CHANNEL_ID>
```

Target future form:

```bash
python3 scripts/send_markdown_report.py --input-path <CONSOLIDATED_REPORT_PATH> --target <DELIVERY_CHANNEL_ID> --sender bot
```

This should be the only automation behavior change required in the digest flow.

## 6. Documentation updates

Update these docs:

- `user_guide.md`
- `AGENTS.md`
- maybe `docs/specification.md` if bot-based delivery becomes the preferred default

Document clearly that:

- source-chat collection still uses user auth
- outbound publication can use a bot
- the two identities are intentionally separate

## Implementation checklist

### Manual setup

- [ ] Create bot in `@BotFather`
- [ ] Store bot token in local secrets
- [ ] Add bot to destination channel
- [ ] Grant posting rights
- [ ] Confirm target channel ID is still correct

### Code

- [ ] Extend config with bot-delivery settings
- [ ] Add bot-client factory
- [ ] Add `--sender {user,bot}` to `send_markdown_report.py`
- [ ] Route delivery through user or bot sender accordingly
- [ ] Keep current chunking behavior intact
- [ ] Add clear error message when bot mode is requested without token

### Tests

- [ ] Add config tests for bot settings
- [ ] Add delivery tests covering sender selection
- [ ] Add fake-client test that verifies chunked sends still happen in order
- [ ] Add a regression test proving user mode remains unchanged

### Docs

- [ ] Update setup guide
- [ ] Update agent guidance
- [ ] Document secrets layout and operational steps

## Acceptance criteria

The migration is done when all of the following are true:

1. The digest can still be collected, summarized, stored, and finalized exactly as before
2. The final publish step can be run with bot sender mode
3. The bot successfully posts the digest into the target channel
4. Alex's own Telegram account is no longer the sender of the digest post
5. Alex's phone receives a normal notification for the new channel post, assuming local notification settings allow it
6. Existing user-mode delivery remains available for fallback/debugging

## Risks and edge cases

### 1. Bot lacks channel rights

Symptom:

- send fails with chat admin or permission-related errors

Mitigation:

- ensure the bot is channel admin with post permission before debugging code

### 2. Private channel targeting issues

Symptom:

- bot cannot resolve or send to the target channel

Mitigation:

- add the bot as a member/admin first
- verify the channel target ID from a real test send

### 3. Formatting differences under bot sender mode

Symptom:

- some Markdown entities render differently or fail

Mitigation:

- test a representative digest with links, bold text, bullet lists, and long multi-chunk output

### 4. Notification still does not appear

Possible causes after migration:

- the channel is muted on the phone
- iOS/Android Telegram notification settings suppress channel alerts
- another Telegram client state issue exists independently of sender identity

Mitigation:

- after the first bot-posted test, verify notification settings before assuming code failure

## Rollback plan

If bot delivery misbehaves, rollback is simple:

- switch cron back to `--sender user` or `TELEGRAM_DELIVERY_MODE=user`
- keep collection/finalization untouched
- continue operating with the old user-posted behavior until bot delivery is fixed

## Recommended order of work when we come back

1. Create and prepare the bot in Telegram
2. Add config support for bot credentials
3. Add sender selection to `send_markdown_report.py`
4. Test manual send to the target channel
5. Update the cron command
6. Run one live digest and confirm phone notification behavior

## Nice-to-have follow-ups

Not required for v1, but useful later:

- support different delivery targets for staging vs production
- add a small dry-run mode for delivery diagnostics
- log sender identity explicitly in delivery output
- optionally move bot delivery to pure Bot API in a later cleanup if we want stricter separation from MTProto user workflows

## Bottom line

The smallest effective fix is:

- keep reading Telegram as Alex
- keep marking source chats as read as Alex
- publish the final digest to the channel as a separate bot

That should solve the main UX problem without forcing a redesign of the summarizer.
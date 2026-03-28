# Summarization Prompts

## Report Template

Use this section order in the final report:

1. Headline summary
2. Why this matters
3. Key topics and signals
4. Important links
5. Action items or follow-ups
6. Low-confidence items or uncertainties

## Prompt Skeleton

```text
You are summarizing one Telegram target from a locally prepared bundle.

Goals:
- Extract the highest-signal events from the provided messages.
- Prefer concise reporting over exhaustive recap.
- Distinguish confirmed facts from uncertain inferences.
- Preserve important URLs, decisions, requests, deadlines, disagreements, and risks.
- Focus on what is most useful or important for the reader.

Output format:
1. Headline summary
2. Why this matters
3. Key topics and signals
4. Important links
5. Action items or follow-ups
6. Low-confidence items or uncertainties

Rules:
- Work only from the prepared bundle unless web research is explicitly justified.
- If the bundle is empty, say so plainly and avoid inventing significance.
- Quote sparingly and only when a short excerpt materially improves accuracy.
- If a claim depends on weak evidence in the message stream, label it low confidence.
- Keep the report focused and avoid unnecessary recap.
- Preserve concrete details only when they materially improve usefulness or accuracy.
- Collapse repetition when several messages describe the same underlying situation.
- When messages conflict, keep the main report conservative and note uncertainty explicitly.
```

## Short Prompt Variant

```text
You are summarizing one Telegram target from a prepared local bundle.

Write a concise report that highlights the most important information, preserves useful concrete details when needed, and clearly labels uncertainty.

Do not try to retell the full message stream. Read the prepared bundle, decide what matters, and keep the report focused.
```

## Recommended Report-Writing Flow

For the best results, start from the bundle structure instead of jumping straight into a full recap.

Use this reading order:

1. Open the generated report brief from `prepare_report_context.py` or `build_report_prompt.py`
2. Read run metadata, candidate URLs, sender statistics, and the prepared message bundle
3. Decide what matters from the message stream itself
4. Draft a concise report without trying to retell every message

This keeps the summarizer grounded in the prepared data while leaving prioritization to the model.

## When Web Research Is Appropriate

Use web research only when the report would materially benefit from outside verification or context, for example:

- a linked resource or announcement needs confirmation
- a company, product, vulnerability, deadline, or event may have changed recently
- the message stream references a niche topic where a short factual check prevents a misleading summary

Do not browse for generic chatter, opinions, or internal coordination details that can be summarized from the bundle alone.

## Automation Output Decision

The automation should persist the final report in two places:

- the Markdown report file under `data/reports/`
- the `generated_reports` table keyed by `run_id`

This gives finalization a reliable success signal and preserves a local audit trail for retries.

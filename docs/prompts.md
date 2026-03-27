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
```

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

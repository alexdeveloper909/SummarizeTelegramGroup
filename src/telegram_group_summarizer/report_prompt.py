from __future__ import annotations

from pathlib import Path
from typing import Optional

from .models import SummaryBundle
from .report_layout import default_report_prompt_path

DEFAULT_REPORT_LANGUAGE = "Ukrainian"


def _forum_report_prompt(bundle: SummaryBundle, report_language: str) -> str:
    lines = [
        "# Report Writing Brief",
        "",
        "Use this brief to write one coherent forum-wide Telegram summary report.",
        "",
        "## Output Contract",
        f"- Language: {report_language}",
        "- Start the report with one source line that names the Telegram forum being summarized.",
        "- Write one report for the whole forum, not one report per topic.",
        "- Be concise, structured, and useful.",
        "- Keep the report conservative when evidence is weak or conflicting.",
        "",
        "## Required Sections",
        "1. Headline summary",
        "2. Cross-topic developments",
        "3. Notable topic threads",
        "4. Important links",
        "5. Actions, requests, decisions, or deadlines",
        "6. Uncertainties if needed",
        "",
        "## Reading Order",
        "1. Run Metadata",
        "2. Forum Overview",
        "3. Topic Radar",
        "4. Candidate URLs",
        "5. Topic Excerpts",
        "6. Other Activity",
        "",
        "## Report Rules",
        "- Use topic boundaries as input, but do not force one output section per topic.",
        "- Summarize the most important developments across the forum first.",
        "- Mention topic names only when they materially improve clarity.",
        "- Combine related topics when that improves readability.",
        "- Collapse minor or repetitive topics into one short sentence or bullet.",
        "- Keep uncertain or weakly evidenced details in an uncertainty section.",
        "",
        "## Run Metadata",
        f"- Run ID: {bundle.run['run_id']}",
        f"- Source Forum Display Name: {bundle.target['display_name']}",
        f"- Source Target Key: {bundle.target['target_key']}",
        f"- Source Target Type: {bundle.target['telegram_entity_type'] or 'unknown'}",
        f"- Source Telegram Entity ID: {bundle.target['telegram_entity_id'] or 'unknown'}",
        f"- Target Mode: {bundle.run['target_mode']}",
        f"- Collected Message Count: {bundle.run['message_count']}",
        f"- Topics Seen: {bundle.run['forum_topic_count']}",
        f"- Active Topics Seen: {bundle.run['forum_active_topic_count']}",
        "",
        "## Forum Overview",
    ]

    if bundle.forum_overview:
        lines.extend(
            [
                f"- Forum Display Name: {bundle.forum_overview['forum_display_name']}",
                f"- Total Topics Seen: {bundle.forum_overview['total_topics_seen']}",
                f"- Active Topics Seen: {bundle.forum_overview['active_topics_seen']}",
                f"- Active Topics Collected: {bundle.forum_overview['active_topics_collected']}",
                f"- Significant Topics: {bundle.forum_overview['significant_topics']}",
                f"- Candidate URL Count: {bundle.forum_overview['candidate_url_count']}",
            ]
        )
    else:
        lines.append("- No forum overview was generated")

    lines.extend(["", "## Topic Radar"])
    if bundle.topic_index:
        for topic in bundle.topic_index:
            collapsed_suffix = " [collapsed]" if topic["collapsed"] else ""
            lines.append(
                f"- {topic['topic_title']}{collapsed_suffix}: "
                f"{topic['collected_message_count']} messages, "
                f"{topic['unique_sender_count']} senders, "
                f"{topic['link_count']} links"
            )
    else:
        lines.append("- No active topics matched this run")

    lines.extend(["", "## Candidate URLs"])
    if bundle.candidate_urls:
        lines.extend(f"- {url}" for url in bundle.candidate_urls)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Final Reminder",
            "- If the forum bundle is sparse, say so plainly.",
            (
                "- Do not omit the source forum; the report must clearly say "
                "which Telegram forum it covers."
            ),
            "- Use the topic radar and excerpts to decide what matters, not raw topic count alone.",
            "",
        ]
    )
    return "\n".join(lines)


def _flat_report_prompt(bundle: SummaryBundle, report_language: str) -> str:
    lines = [
        "# Report Writing Brief",
        "",
        "Use this brief to write the final Telegram summary report.",
        "",
        "## Output Contract",
        f"- Language: {report_language}",
        (
            "- Start the report with one source line that names the Telegram group or "
            "channel being summarized."
        ),
        "- Be concise, structured, and useful.",
        "- Decide from the prepared bundle what matters most.",
        "- Keep the report conservative when evidence is weak or conflicting.",
        "",
        "## Required Sections",
        "1. Headline summary",
        "2. Key topics and signals",
        "3. Important links",
        "4. Action items or follow-ups",
        "",
        "## Reading Order",
        "1. Run Metadata",
        "2. Candidate URLs",
        "3. Sender Statistics",
        "4. Full Chronological Messages",
        "",
        "## Report Rules",
        (
            "- Work from the prepared bundle and decide what is important without relying "
            "on pre-labeled signals."
        ),
        "- Preserve concrete details when they materially improve the report.",
        "- If claims are weak, disputed, or incomplete, say so clearly.",
        "- Keep the report readable and avoid unnecessary detail.",
        "",
        "## Run Metadata",
        f"- Run ID: {bundle.run['run_id']}",
        f"- Source Target Display Name: {bundle.target['display_name']}",
        f"- Source Target Key: {bundle.target['target_key']}",
        f"- Source Target Type: {bundle.target['telegram_entity_type'] or 'unknown'}",
        f"- Source Telegram Entity ID: {bundle.target['telegram_entity_id'] or 'unknown'}",
        f"- Mode: {bundle.run['mode'] or 'unknown'}",
        f"- Message Count: {bundle.run['message_count']}",
        f"- Reply Thread Roots: {len(bundle.reply_threads)}",
        "",
        "## Candidate URLs",
    ]

    if bundle.candidate_urls:
        lines.extend(f"- {url}" for url in bundle.candidate_urls)
    else:
        lines.append("- None")

    lines.extend(["", "## Sender Statistics"])
    if bundle.sender_stats:
        lines.extend(f"- {stat.sender_name}: {stat.message_count}" for stat in bundle.sender_stats)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Final Reminder",
            "- If the bundle is empty or low-value, say so plainly.",
            (
                "- Do not omit the source target; the final report must clearly say "
                "which Telegram group or channel it covers."
            ),
            "- Use the chronological messages to decide what is important.",
            "",
        ]
    )
    return "\n".join(lines)


def build_report_prompt(
    bundle: SummaryBundle,
    *,
    report_language: str = DEFAULT_REPORT_LANGUAGE,
) -> str:
    if bundle.target["is_forum"]:
        return _forum_report_prompt(bundle, report_language)
    return _flat_report_prompt(bundle, report_language)


def write_report_prompt(
    bundle: SummaryBundle,
    *,
    output_path: Optional[Path],
    reports_dir: Path,
    report_language: str = DEFAULT_REPORT_LANGUAGE,
) -> Path:
    final_output_path = output_path or default_report_prompt_path(
        reports_dir,
        str(bundle.run["run_id"]),
        str(bundle.run["started_at"]),
    )
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_text(
        build_report_prompt(bundle, report_language=report_language),
        encoding="utf-8",
    )
    return final_output_path

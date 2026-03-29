from __future__ import annotations

from pathlib import Path
from typing import Optional

from .models import SummaryBundle
from .report_layout import default_report_prompt_path

DEFAULT_REPORT_LANGUAGE = "Ukrainian"


def build_report_prompt(
    bundle: SummaryBundle,
    *,
    report_language: str = DEFAULT_REPORT_LANGUAGE,
) -> str:
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
        "2. Why this matters",
        "3. Key topics and signals",
        "4. Important links",
        "5. Action items or follow-ups",
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

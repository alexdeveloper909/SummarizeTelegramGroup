from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from telegram_group_summarizer.report_layout import (
    artifact_directory_path,
    classify_legacy_report_file,
    default_report_path,
    default_report_prompt_path,
    default_summary_output_prefix,
    report_date_folder_name,
)


class ReportLayoutTests(unittest.TestCase):
    def test_default_paths_use_dated_artifact_directories(self) -> None:
        reports_dir = Path("/tmp/reports")
        started_at = "2026-03-28T20:28:41.167815+00:00"

        self.assertEqual("28.03.2026", report_date_folder_name(started_at))
        self.assertEqual(
            Path("/tmp/reports/28.03.2026/summary/run-1.summary"),
            default_summary_output_prefix(reports_dir, "run-1", started_at),
        )
        self.assertEqual(
            Path("/tmp/reports/28.03.2026/report_prompt/run-1.report_prompt.md"),
            default_report_prompt_path(reports_dir, "run-1", started_at),
        )
        self.assertEqual(
            Path("/tmp/reports/28.03.2026/report/run-1.report.md"),
            default_report_path(reports_dir, "run-1", started_at),
        )

    def test_artifact_directory_path_creates_standard_day_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reports_dir = Path(tmpdir) / "reports"
            started_at = "2026-03-28T20:28:41.167815+00:00"
            path = artifact_directory_path(reports_dir, started_at, "draft")
            self.assertEqual(reports_dir / "28.03.2026" / "draft", path)
            for directory_name in (
                "final",
                "report",
                "report_prompt",
                "summary",
                "draft",
            ):
                self.assertTrue((reports_dir / "28.03.2026" / directory_name).exists())

    def test_classify_legacy_report_file_normalizes_known_suffixes(self) -> None:
        summary_json = classify_legacy_report_file(Path("45dacb69bf9c4519ad27336a4318fa96.json"))
        summary_markdown = classify_legacy_report_file(
            Path("45dacb69bf9c4519ad27336a4318fa96.md")
        )
        report_prompt = classify_legacy_report_file(
            Path("45dacb69bf9c4519ad27336a4318fa96.report_prompt.md")
        )
        draft = classify_legacy_report_file(Path("f5b82128493b409cbd0402781a58172f.draft.uk.md"))
        final = classify_legacy_report_file(
            Path("10492ab100ff4f52891a5d0ad94cf929.agent_report.md")
        )

        self.assertEqual("summary", summary_json.artifact_directory)
        self.assertEqual("45dacb69bf9c4519ad27336a4318fa96.summary.json", summary_json.filename)
        self.assertEqual("summary", summary_markdown.artifact_directory)
        self.assertEqual("45dacb69bf9c4519ad27336a4318fa96.summary.md", summary_markdown.filename)
        self.assertEqual("report_prompt", report_prompt.artifact_directory)
        self.assertEqual("draft", draft.artifact_directory)
        self.assertEqual("final", final.artifact_directory)


if __name__ == "__main__":
    unittest.main()

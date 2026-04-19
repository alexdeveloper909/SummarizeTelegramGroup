from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class ScriptEntrypointTests(unittest.TestCase):
    def test_scripts_run_help_without_pythonpath_bootstrapping(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        scripts = [
            "scripts/auth_telegram.py",
            "scripts/build_consolidated_digest.py",
            "scripts/build_report_prompt.py",
            "scripts/collect_digest_context.py",
            "scripts/collect_messages.py",
            "scripts/finalize_run.py",
            "scripts/migrate_report_layout.py",
            "scripts/prepare_report_context.py",
            "scripts/prepare_summary_input.py",
            "scripts/purge_old_runs.py",
            "scripts/store_report.py",
        ]

        for script in scripts:
            with self.subTest(script=script):
                completed = subprocess.run(
                    [sys.executable, script, "--help"],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    0,
                    completed.returncode,
                    msg=completed.stderr or completed.stdout,
                )


if __name__ == "__main__":
    unittest.main()

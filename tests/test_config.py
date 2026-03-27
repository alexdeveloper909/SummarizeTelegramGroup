from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telegram_group_summarizer.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_rejects_invalid_lookback_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            env = {
                "TELEGRAM_SUMMARIZER_DEFAULT_LOOKBACK_HOURS": "48",
                "TELEGRAM_SUMMARIZER_MAX_LOOKBACK_HOURS": "24",
            }
            with patch.dict(os.environ, env, clear=False):
                with self.assertRaises(ValueError):
                    load_config(repo_root=repo_root)

    def test_validate_telegram_credentials_reports_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(repo_root=repo_root)
                with self.assertRaises(ValueError):
                    config.validate_telegram_credentials()


if __name__ == "__main__":
    unittest.main()

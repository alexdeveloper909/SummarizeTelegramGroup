from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telegram_group_summarizer.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_reads_local_secret_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            secret_dir = repo_root / ".secrets"
            secret_dir.mkdir(parents=True)
            (secret_dir / "telegram.env").write_text(
                "\n".join(
                    [
                        "TELEGRAM_API_ID=12345",
                        "TELEGRAM_API_HASH=hash-from-file",
                        "TELEGRAM_PHONE=+1234567890",
                        "TELEGRAM_PASSWORD=file-password",
                        "TELEGRAM_SESSION_NAME=file_session",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(repo_root=repo_root)

            self.assertEqual("12345", config.telegram_api_id)
            self.assertEqual("hash-from-file", config.telegram_api_hash)
            self.assertEqual("+1234567890", config.telegram_phone)
            self.assertEqual("file-password", config.telegram_password)
            self.assertEqual("file_session", config.session_name)

    def test_environment_variables_override_local_secret_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            secret_dir = repo_root / ".secrets"
            secret_dir.mkdir(parents=True)
            (secret_dir / "telegram.env").write_text(
                "TELEGRAM_API_ID=12345\nTELEGRAM_API_HASH=file-hash\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "TELEGRAM_API_ID": "99999",
                    "TELEGRAM_API_HASH": "env-hash",
                    "TELEGRAM_PHONE": "+19999999999",
                    "TELEGRAM_PASSWORD": "env-password",
                },
                clear=True,
            ):
                config = load_config(repo_root=repo_root)

            self.assertEqual("99999", config.telegram_api_id)
            self.assertEqual("env-hash", config.telegram_api_hash)
            self.assertEqual("+19999999999", config.telegram_phone)
            self.assertEqual("env-password", config.telegram_password)

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

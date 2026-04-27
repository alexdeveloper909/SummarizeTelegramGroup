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
                        "TELEGRAM_DELIVERY_MODE=bot",
                        "TELEGRAM_BOT_TOKEN=bot-token",
                        "TELEGRAM_BOT_SESSION_NAME=bot_session",
                        "TELEGRAM_DELIVERY_CHAT_ID=<DELIVERY_CHAT_ID>",
                        "TELEGRAM_DELIVERY_TOPIC_ID=123",
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
            self.assertEqual("bot", config.telegram_delivery_mode)
            self.assertEqual("bot-token", config.telegram_bot_token)
            self.assertEqual("bot_session", config.telegram_bot_session_name)
            self.assertEqual("<DELIVERY_CHAT_ID>", config.telegram_delivery_chat_id)
            self.assertEqual(123, config.telegram_delivery_topic_id)

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

    def test_validate_bot_delivery_credentials_reports_missing_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".secrets").mkdir(parents=True)
            (repo_root / ".secrets" / "telegram.env").write_text(
                "TELEGRAM_API_ID=12345\nTELEGRAM_API_HASH=hash\nTELEGRAM_DELIVERY_MODE=bot\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(repo_root=repo_root)
                with self.assertRaises(ValueError):
                    config.validate_bot_delivery_credentials()

    def test_bot_secret_file_is_loaded_after_main_telegram_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".secrets").mkdir(parents=True)
            (repo_root / ".secrets" / "telegram.env").write_text(
                "TELEGRAM_API_ID=12345\nTELEGRAM_API_HASH=hash\nTELEGRAM_DELIVERY_MODE=bot\n",
                encoding="utf-8",
            )
            (repo_root / ".secrets" / "telegram_bot.env").write_text(
                "TELEGRAM_BOT_TOKEN=bot-token\nTELEGRAM_DELIVERY_CHAT_ID=<DELIVERY_CHAT_ID>\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(repo_root=repo_root)
            self.assertEqual("bot-token", config.telegram_bot_token)
            self.assertEqual("<DELIVERY_CHAT_ID>", config.telegram_delivery_chat_id)


if __name__ == "__main__":
    unittest.main()

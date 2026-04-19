from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from telegram_group_summarizer.digest_config import (
    DigestConfigError,
    load_digest_job_config,
    resolve_digest_runtime_options,
)


class DigestConfigTests(unittest.TestCase):
    def test_load_digest_job_config_reads_targets_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "digest.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "Evening Digest",
                        "delivery_target": "-1001",
                        "targets": [
                            {
                                "target": "-100123",
                                "label": "Builders",
                                "target_mode": "chat",
                            },
                            {
                                "target": "-100456",
                                "label": "Forum",
                                "target_mode": "forum",
                                "forum_max_messages_per_topic": 80,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            config = load_digest_job_config(path)
            runtime = resolve_digest_runtime_options(config, lookback_hours=48)

            self.assertEqual("Evening Digest", config.name)
            self.assertEqual("lookback-only", config.collection_strategy)
            self.assertEqual("-1001", config.delivery_target)
            self.assertEqual(2, len(runtime.targets))
            self.assertEqual(48, runtime.lookback_hours)
            self.assertEqual("Builders", runtime.targets[0].label)
            self.assertEqual("forum", runtime.targets[1].target_mode)
            self.assertEqual(80, runtime.targets[1].forum_max_messages_per_topic)

    def test_invalid_collection_strategy_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "digest.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "Bad Digest",
                        "collection_strategy": "chaos",
                        "targets": [{"target": "-100123"}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(DigestConfigError):
                load_digest_job_config(path)


if __name__ == "__main__":
    unittest.main()

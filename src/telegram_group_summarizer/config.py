from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_MAX_MESSAGES = 500
DEFAULT_BUSY_TIMEOUT_MS = 5000
DEFAULT_LOG_LEVEL = "INFO"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer.") from exc


@dataclass(frozen=True)
class AppConfig:
    repo_root: Path
    db_path: Path
    reports_dir: Path
    sessions_dir: Path
    logs_dir: Path
    telegram_api_id: Optional[str]
    telegram_api_hash: Optional[str]
    session_name: str
    default_lookback_hours: int
    max_lookback_hours: int
    default_max_messages: int
    sqlite_busy_timeout_ms: int
    log_level: str

    def validate_telegram_credentials(self) -> None:
        missing = []
        if not self.telegram_api_id:
            missing.append("TELEGRAM_API_ID")
        if not self.telegram_api_hash:
            missing.append("TELEGRAM_API_HASH")
        if missing:
            names = ", ".join(missing)
            raise ValueError(f"Missing required Telegram credentials: {names}")


def load_config(repo_root: Optional[Path] = None) -> AppConfig:
    root = repo_root or _repo_root()
    data_dir = root / "data"
    db_path = Path(os.getenv("TELEGRAM_SUMMARIZER_DB_PATH", data_dir / "sqlite" / "telegram_group_summarizer.db"))
    reports_dir = Path(os.getenv("TELEGRAM_SUMMARIZER_REPORTS_DIR", data_dir / "reports"))
    sessions_dir = Path(os.getenv("TELEGRAM_SUMMARIZER_SESSIONS_DIR", data_dir / "sessions"))
    logs_dir = Path(os.getenv("TELEGRAM_SUMMARIZER_LOGS_DIR", root / "logs"))
    session_name = os.getenv("TELEGRAM_SESSION_NAME", "telegram_group_summarizer")

    default_lookback_hours = _int_from_env("TELEGRAM_SUMMARIZER_DEFAULT_LOOKBACK_HOURS", DEFAULT_LOOKBACK_HOURS)
    max_lookback_hours = _int_from_env("TELEGRAM_SUMMARIZER_MAX_LOOKBACK_HOURS", DEFAULT_LOOKBACK_HOURS)
    default_max_messages = _int_from_env("TELEGRAM_SUMMARIZER_DEFAULT_MAX_MESSAGES", DEFAULT_MAX_MESSAGES)
    sqlite_busy_timeout_ms = _int_from_env("TELEGRAM_SUMMARIZER_SQLITE_BUSY_TIMEOUT_MS", DEFAULT_BUSY_TIMEOUT_MS)
    log_level = os.getenv("TELEGRAM_SUMMARIZER_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()

    if default_lookback_hours <= 0:
        raise ValueError("Default lookback hours must be positive.")
    if max_lookback_hours <= 0:
        raise ValueError("Maximum lookback hours must be positive.")
    if default_lookback_hours > max_lookback_hours:
        raise ValueError("Default lookback hours cannot exceed the maximum lookback window.")
    if default_max_messages <= 0:
        raise ValueError("Default max messages must be positive.")
    if sqlite_busy_timeout_ms < 0:
        raise ValueError("SQLite busy timeout must be zero or positive.")

    return AppConfig(
        repo_root=root,
        db_path=db_path,
        reports_dir=reports_dir,
        sessions_dir=sessions_dir,
        logs_dir=logs_dir,
        telegram_api_id=os.getenv("TELEGRAM_API_ID"),
        telegram_api_hash=os.getenv("TELEGRAM_API_HASH"),
        session_name=session_name,
        default_lookback_hours=default_lookback_hours,
        max_lookback_hours=max_lookback_hours,
        default_max_messages=default_max_messages,
        sqlite_busy_timeout_ms=sqlite_busy_timeout_ms,
        log_level=log_level,
    )

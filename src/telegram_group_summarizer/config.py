from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_MAX_MESSAGES = 500
DEFAULT_BUSY_TIMEOUT_MS = 5000
DEFAULT_LOG_LEVEL = "INFO"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_local_env(repo_root: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    candidates = [
        repo_root / ".secrets" / "telegram.env",
        repo_root / ".env.local",
        repo_root / ".env",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        lines = candidate.read_text(encoding="utf-8").splitlines()
        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                raise ValueError(
                    f"Invalid line in {candidate}:{line_number}. "
                    "Expected KEY=VALUE format."
                )
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                raise ValueError(
                    f"Invalid line in {candidate}:{line_number}. "
                    "Missing environment variable name."
                )
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[key] = value
    return values


def _env_value(name: str, file_env: Optional[Dict[str, str]] = None) -> Optional[str]:
    if name in os.environ:
        return os.environ[name]
    if file_env is None:
        return None
    return file_env.get(name)


def _int_from_env(name: str, default: int, file_env: Optional[Dict[str, str]] = None) -> int:
    raw_value = _env_value(name, file_env)
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
    telegram_phone: Optional[str] = None
    telegram_password: Optional[str] = None

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
    file_env = _load_local_env(root)
    data_dir = root / "data"
    db_path = Path(
        _env_value("TELEGRAM_SUMMARIZER_DB_PATH", file_env)
        or data_dir / "sqlite" / "telegram_group_summarizer.db"
    )
    reports_dir = Path(
        _env_value("TELEGRAM_SUMMARIZER_REPORTS_DIR", file_env) or data_dir / "reports"
    )
    sessions_dir = Path(
        _env_value("TELEGRAM_SUMMARIZER_SESSIONS_DIR", file_env) or data_dir / "sessions"
    )
    logs_dir = Path(_env_value("TELEGRAM_SUMMARIZER_LOGS_DIR", file_env) or root / "logs")
    session_name = _env_value("TELEGRAM_SESSION_NAME", file_env) or "telegram_group_summarizer"

    default_lookback_hours = _int_from_env(
        "TELEGRAM_SUMMARIZER_DEFAULT_LOOKBACK_HOURS",
        DEFAULT_LOOKBACK_HOURS,
        file_env,
    )
    max_lookback_hours = _int_from_env(
        "TELEGRAM_SUMMARIZER_MAX_LOOKBACK_HOURS",
        DEFAULT_LOOKBACK_HOURS,
        file_env,
    )
    default_max_messages = _int_from_env(
        "TELEGRAM_SUMMARIZER_DEFAULT_MAX_MESSAGES",
        DEFAULT_MAX_MESSAGES,
        file_env,
    )
    sqlite_busy_timeout_ms = _int_from_env(
        "TELEGRAM_SUMMARIZER_SQLITE_BUSY_TIMEOUT_MS",
        DEFAULT_BUSY_TIMEOUT_MS,
        file_env,
    )
    log_level = (_env_value("TELEGRAM_SUMMARIZER_LOG_LEVEL", file_env) or DEFAULT_LOG_LEVEL).upper()

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
        telegram_api_id=_env_value("TELEGRAM_API_ID", file_env),
        telegram_api_hash=_env_value("TELEGRAM_API_HASH", file_env),
        telegram_phone=_env_value("TELEGRAM_PHONE", file_env),
        telegram_password=_env_value("TELEGRAM_PASSWORD", file_env),
        session_name=session_name,
        default_lookback_hours=default_lookback_hours,
        max_lookback_hours=max_lookback_hours,
        default_max_messages=default_max_messages,
        sqlite_busy_timeout_ms=sqlite_busy_timeout_ms,
        log_level=log_level,
    )

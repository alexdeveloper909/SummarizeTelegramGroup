from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .collection import VALID_COLLECTION_STRATEGIES, VALID_TARGET_MODES
from .config import DEFAULT_LOOKBACK_HOURS, DEFAULT_MAX_MESSAGES
from .report_prompt import DEFAULT_REPORT_LANGUAGE


@dataclass(frozen=True)
class DigestTargetConfig:
    target: str
    label: Optional[str] = None
    target_mode: str = "auto"
    max_messages: Optional[int] = None
    forum_topic_limit: Optional[int] = None
    forum_topic_probe_messages: Optional[int] = None
    forum_max_messages_per_topic: Optional[int] = None


@dataclass(frozen=True)
class DigestJobConfig:
    name: str
    targets: list[DigestTargetConfig]
    report_language: str = DEFAULT_REPORT_LANGUAGE
    delivery_target: Optional[str] = None
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS
    max_messages: int = DEFAULT_MAX_MESSAGES
    collection_strategy: str = "lookback-only"


@dataclass(frozen=True)
class DigestTargetRuntimeOptions:
    target: str
    label: Optional[str]
    target_mode: str
    max_messages: int
    forum_topic_limit: Optional[int]
    forum_topic_probe_messages: Optional[int]
    forum_max_messages_per_topic: Optional[int]


@dataclass(frozen=True)
class DigestRuntimeOptions:
    name: str
    targets: list[DigestTargetRuntimeOptions]
    report_language: str
    delivery_target: Optional[str]
    lookback_hours: int
    max_messages: int
    collection_strategy: str


class DigestConfigError(ValueError):
    pass


def _expect_mapping(payload: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DigestConfigError(f"{context} must be a JSON object.")
    return payload


def _optional_positive_int(value: Any, *, field_name: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise DigestConfigError(f"{field_name} must be a positive integer when provided.")
    return value


def _required_positive_int(value: Any, *, field_name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise DigestConfigError(f"{field_name} must be a positive integer.")
    return value


def _optional_string(value: Any, *, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DigestConfigError(f"{field_name} must be a non-empty string when provided.")
    return value.strip()


def _required_string(value: Any, *, field_name: str) -> str:
    parsed = _optional_string(value, field_name=field_name)
    if parsed is None:
        raise DigestConfigError(f"{field_name} is required.")
    return parsed


def _parse_target(index: int, payload: Any) -> DigestTargetConfig:
    item = _expect_mapping(payload, context=f"targets[{index}]")
    target_mode = item.get("target_mode", "auto")
    if target_mode not in VALID_TARGET_MODES:
        raise DigestConfigError(
            f"targets[{index}].target_mode must be one of {sorted(VALID_TARGET_MODES)}."
        )
    return DigestTargetConfig(
        target=_required_string(item.get("target"), field_name=f"targets[{index}].target"),
        label=_optional_string(item.get("label"), field_name=f"targets[{index}].label"),
        target_mode=target_mode,
        max_messages=_optional_positive_int(
            item.get("max_messages"), field_name=f"targets[{index}].max_messages"
        ),
        forum_topic_limit=_optional_positive_int(
            item.get("forum_topic_limit"), field_name=f"targets[{index}].forum_topic_limit"
        ),
        forum_topic_probe_messages=_optional_positive_int(
            item.get("forum_topic_probe_messages"),
            field_name=f"targets[{index}].forum_topic_probe_messages",
        ),
        forum_max_messages_per_topic=_optional_positive_int(
            item.get("forum_max_messages_per_topic"),
            field_name=f"targets[{index}].forum_max_messages_per_topic",
        ),
    )


def load_digest_job_config(path: Path) -> DigestJobConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    root = _expect_mapping(payload, context=str(path))

    collection_strategy = root.get("collection_strategy", "lookback-only")
    if collection_strategy not in VALID_COLLECTION_STRATEGIES:
        raise DigestConfigError(
            f"collection_strategy must be one of {sorted(VALID_COLLECTION_STRATEGIES)}."
        )

    raw_targets = root.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise DigestConfigError("targets must be a non-empty array.")

    targets = [_parse_target(index, item) for index, item in enumerate(raw_targets)]

    return DigestJobConfig(
        name=_required_string(root.get("name"), field_name="name"),
        targets=targets,
        report_language=(
            _optional_string(root.get("report_language"), field_name="report_language")
            or DEFAULT_REPORT_LANGUAGE
        ),
        delivery_target=_optional_string(
            root.get("delivery_target"), field_name="delivery_target"
        ),
        lookback_hours=_required_positive_int(
            root.get("lookback_hours", DEFAULT_LOOKBACK_HOURS),
            field_name="lookback_hours",
        ),
        max_messages=_required_positive_int(
            root.get("max_messages", DEFAULT_MAX_MESSAGES),
            field_name="max_messages",
        ),
        collection_strategy=collection_strategy,
    )


def resolve_digest_runtime_options(
    job_config: DigestJobConfig,
    *,
    lookback_hours: Optional[int] = None,
    max_messages: Optional[int] = None,
    collection_strategy: Optional[str] = None,
    report_language: Optional[str] = None,
    delivery_target: Optional[str] = None,
) -> DigestRuntimeOptions:
    effective_collection_strategy = collection_strategy or job_config.collection_strategy
    if effective_collection_strategy not in VALID_COLLECTION_STRATEGIES:
        raise DigestConfigError(
            "collection_strategy must be one of "
            f"{sorted(VALID_COLLECTION_STRATEGIES)}."
        )

    effective_lookback_hours = lookback_hours or job_config.lookback_hours
    effective_max_messages = max_messages or job_config.max_messages
    if effective_lookback_hours <= 0:
        raise DigestConfigError("lookback_hours must be positive.")
    if effective_max_messages <= 0:
        raise DigestConfigError("max_messages must be positive.")

    runtime_targets = [
        DigestTargetRuntimeOptions(
            target=target.target,
            label=target.label,
            target_mode=target.target_mode,
            max_messages=target.max_messages or effective_max_messages,
            forum_topic_limit=target.forum_topic_limit,
            forum_topic_probe_messages=target.forum_topic_probe_messages,
            forum_max_messages_per_topic=target.forum_max_messages_per_topic,
        )
        for target in job_config.targets
    ]

    return DigestRuntimeOptions(
        name=job_config.name,
        targets=runtime_targets,
        report_language=report_language or job_config.report_language,
        delivery_target=delivery_target or job_config.delivery_target,
        lookback_hours=effective_lookback_hours,
        max_messages=effective_max_messages,
        collection_strategy=effective_collection_strategy,
    )

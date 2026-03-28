from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple

from .collection import derive_target_reference

MAX_TELEGRAM_MESSAGE_UTF16 = 4096


Formatter = Tuple[
    Callable[[str], tuple[str, list[object]]],
    Callable[[str, list[object], int], list[tuple[str, list[object]]]],
]


@dataclass(frozen=True)
class OutboundMessageChunk:
    text: str
    formatting_entities: tuple[object, ...]


def read_markdown_report(input_path: Path) -> str:
    markdown_text = input_path.read_text(encoding="utf-8")
    if not markdown_text.strip():
        raise ValueError(f"Report file {input_path} is empty.")
    return markdown_text


def _load_formatter() -> Formatter:
    try:
        from telegramify_markdown import convert, split_entities
    except ImportError as exc:
        raise RuntimeError(
            "telegramify-markdown is required for report delivery. "
            "Install it with `pip install -e '.[telegram,dev]'` using Python 3.10 or newer."
        ) from exc

    def split_wrapper(
        text: str, entities: list[object], max_utf16_len: int
    ) -> list[tuple[str, list[object]]]:
        return list(split_entities(text, entities, max_utf16_len=max_utf16_len))

    return convert, split_wrapper


def _load_telethon_types():
    try:
        from telethon.tl import types as telethon_types
    except ImportError as exc:
        raise RuntimeError(
            "Telethon is required for Telegram delivery. "
            "Install it with `pip install -e '.[telegram,dev]'`."
        ) from exc
    return telethon_types


def _build_telethon_entity(entity: object, telethon_types) -> object:
    entity_type = getattr(entity, "type", None)
    offset = int(getattr(entity, "offset"))
    length = int(getattr(entity, "length"))

    if entity_type == "bold":
        return telethon_types.MessageEntityBold(offset=offset, length=length)
    if entity_type == "italic":
        return telethon_types.MessageEntityItalic(offset=offset, length=length)
    if entity_type == "underline":
        return telethon_types.MessageEntityUnderline(offset=offset, length=length)
    if entity_type == "strikethrough":
        return telethon_types.MessageEntityStrike(offset=offset, length=length)
    if entity_type == "spoiler":
        return telethon_types.MessageEntitySpoiler(offset=offset, length=length)
    if entity_type == "code":
        return telethon_types.MessageEntityCode(offset=offset, length=length)
    if entity_type == "pre":
        language = getattr(entity, "language", None) or ""
        return telethon_types.MessageEntityPre(offset=offset, length=length, language=language)
    if entity_type == "text_link":
        url = getattr(entity, "url", None)
        if not url:
            raise ValueError("text_link entities require a URL.")
        return telethon_types.MessageEntityTextUrl(offset=offset, length=length, url=url)
    if entity_type in {"blockquote", "expandable_blockquote"}:
        collapsed = entity_type == "expandable_blockquote"
        try:
            return telethon_types.MessageEntityBlockquote(
                offset=offset,
                length=length,
                collapsed=collapsed,
            )
        except TypeError:
            return telethon_types.MessageEntityBlockquote(offset=offset, length=length)
    if entity_type == "custom_emoji":
        custom_emoji_id = getattr(entity, "custom_emoji_id", None)
        if not custom_emoji_id:
            raise ValueError("custom_emoji entities require a custom_emoji_id.")
        return telethon_types.MessageEntityCustomEmoji(
            offset=offset,
            length=length,
            document_id=int(custom_emoji_id),
        )

    raise ValueError(f"Unsupported telegramify-markdown entity type: {entity_type!r}")


def convert_telegramify_entities(
    entities: Iterable[object],
    *,
    telethon_types=None,
) -> tuple[object, ...]:
    types_module = telethon_types or _load_telethon_types()
    return tuple(_build_telethon_entity(entity, types_module) for entity in entities)


def build_message_chunks(
    markdown_text: str,
    *,
    max_message_length: int = MAX_TELEGRAM_MESSAGE_UTF16,
    formatter: Optional[Formatter] = None,
    telethon_types=None,
) -> list[OutboundMessageChunk]:
    if max_message_length <= 0:
        raise ValueError("Maximum message length must be positive.")
    if not markdown_text.strip():
        raise ValueError("Report Markdown is empty.")

    convert, split_entities = formatter or _load_formatter()
    text, entities = convert(markdown_text)
    if not text.strip():
        raise ValueError("Report Markdown produced no sendable Telegram text.")

    chunks = [
        OutboundMessageChunk(
            text=chunk_text,
            formatting_entities=convert_telegramify_entities(
                chunk_entities,
                telethon_types=telethon_types,
            ),
        )
        for chunk_text, chunk_entities in split_entities(
            text,
            entities,
            max_message_length,
        )
        if chunk_text
    ]
    if not chunks:
        raise ValueError("Report Markdown produced no sendable Telegram text.")
    return chunks


async def send_markdown_report(
    *,
    connection,
    telegram_client,
    target_value: str,
    markdown_text: str,
    link_preview: bool = False,
    max_message_length: int = MAX_TELEGRAM_MESSAGE_UTF16,
    formatter: Optional[Formatter] = None,
    telethon_types=None,
) -> dict:
    reference = derive_target_reference(connection, target_value)
    resolved_target = await telegram_client.resolve_target(reference)
    chunks = build_message_chunks(
        markdown_text,
        max_message_length=max_message_length,
        formatter=formatter,
        telethon_types=telethon_types,
    )

    sent_message_ids = []
    for chunk in chunks:
        sent_message = await telegram_client.send_text_message(
            resolved_target,
            chunk.text,
            formatting_entities=chunk.formatting_entities,
            link_preview=link_preview,
        )
        message_id = getattr(sent_message, "id", None)
        if message_id is not None:
            sent_message_ids.append(int(message_id))

    return {
        "target_key": resolved_target.target_key,
        "target_display_name": resolved_target.display_name,
        "chunk_count": len(chunks),
        "message_ids": sent_message_ids,
    }

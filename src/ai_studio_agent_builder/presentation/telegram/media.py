"""Telegram media classification and safe local download."""

import logging
from pathlib import Path
from typing import BinaryIO, TypeVar, cast
from uuid import uuid4

from aiogram import Bot, types
from aiogram.types import ContentType, Message

from ai_studio_agent_builder.application.file_policy import (
    MAX_UPLOAD_BYTES,
    sanitize_filename,
)
from ai_studio_agent_builder.application.interaction import UploadValidationError


T = TypeVar("T")


class _BoundedBinaryWriter:
    def __init__(self, destination: BinaryIO, *, limit: int) -> None:
        self._destination = destination
        self._limit = limit
        self._size = 0

    def write(self, chunk: bytes) -> int:
        next_size = self._size + len(chunk)
        if next_size > self._limit:
            raise UploadValidationError(
                f"Upload exceeds the {self._limit}-byte file limit"
            )
        written = self._destination.write(chunk)
        self._size = next_size
        return written

    def flush(self) -> None:
        self._destination.flush()


def _require(value: T | None, description: str) -> T:
    if value is None:
        raise ValueError(f"Message is missing {description}")
    return value


async def download_media(bot: Bot, message: types.Message, base_dir: Path) -> str:
    """Download Telegram media and return its safe local filename."""

    file_id = None
    filename = "unknown.bin"
    declared_size: int | None = None
    logging.info("Message type=%s", message.content_type)
    if message.content_type == ContentType.PHOTO:
        photo = _require(message.photo, "photo attachment")
        if not photo:
            raise ValueError("Message photo list is empty")
        file_id = photo[-1].file_id
        declared_size = photo[-1].file_size
        filename = f"photo_{message.message_id}.jpg"
    elif message.content_type == ContentType.DOCUMENT:
        document = _require(message.document, "document attachment")
        file_id = document.file_id
        declared_size = document.file_size
        filename = document.file_name or f"doc_{message.message_id}"
    elif message.content_type == ContentType.AUDIO:
        audio = _require(message.audio, "audio attachment")
        file_id = audio.file_id
        declared_size = audio.file_size
        filename = audio.file_name or f"audio_{message.message_id}.mp3"
    elif message.content_type == ContentType.VIDEO:
        video = _require(message.video, "video attachment")
        file_id = video.file_id
        declared_size = video.file_size
        filename = video.file_name or f"video_{message.message_id}.mp4"
    elif message.content_type == ContentType.VOICE:
        voice = _require(message.voice, "voice attachment")
        file_id = voice.file_id
        declared_size = voice.file_size
        filename = f"voice_{message.message_id}.ogg"
    elif message.content_type == ContentType.VIDEO_NOTE:
        video_note = _require(message.video_note, "video note attachment")
        file_id = video_note.file_id
        declared_size = video_note.file_size
        filename = f"videonote_{message.message_id}.mp4"
    elif message.content_type == ContentType.ANIMATION:
        animation = _require(message.animation, "animation attachment")
        file_id = animation.file_id
        declared_size = animation.file_size
        filename = animation.file_name or f"anim_{message.message_id}.gif"
    elif message.content_type == ContentType.STICKER:
        sticker = _require(message.sticker, "sticker attachment")
        file_id = sticker.file_id
        declared_size = sticker.file_size
        filename = f"sticker_{message.message_id}.webp"
    else:
        raise ValueError(f"Unsupported media type: {message.content_type}")

    _validate_declared_size(declared_size)
    telegram_file = await bot.get_file(_require(file_id, "file id"))
    _validate_declared_size(getattr(telegram_file, "file_size", None))
    file_path = _require(telegram_file.file_path, "telegram file path")

    safe_name = sanitize_download_filename(filename)
    local_path = base_dir / safe_name
    partial_path = base_dir / f".{safe_name}.{uuid4().hex}.partial"
    logging.info("Saving Telegram file path=%s", local_path)
    base_dir.mkdir(parents=True, exist_ok=True)
    try:
        with partial_path.open("xb") as destination:
            await bot.download_file(
                file_path,
                destination=cast(
                    BinaryIO,
                    _BoundedBinaryWriter(
                        destination,
                        limit=MAX_UPLOAD_BYTES,
                    ),
                ),
                seek=False,
            )
        partial_path.replace(local_path)
    except BaseException:
        partial_path.unlink(missing_ok=True)
        raise
    return safe_name


def _validate_declared_size(size: int | None) -> None:
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise UploadValidationError(
            f"Upload is {size} bytes; limit is {MAX_UPLOAD_BYTES} bytes"
        )


def sanitize_download_filename(filename: str) -> str:
    return sanitize_filename(filename, fallback="download.bin")


def classify_message(message: Message) -> str:
    if message.content_type == ContentType.TEXT:
        return "only_text"
    if message.caption:
        return "text_file"
    return "only_file"


__all__ = ["classify_message", "download_media", "sanitize_download_filename"]

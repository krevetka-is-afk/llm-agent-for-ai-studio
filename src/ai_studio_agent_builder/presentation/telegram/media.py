"""Telegram media classification and safe local download."""

import logging
from pathlib import Path
from typing import TypeVar

import aiofiles
from aiogram import Bot, types
from aiogram.types import ContentType, Message

from ai_studio_agent_builder.application.file_policy import sanitize_filename


T = TypeVar("T")


def _require(value: T | None, description: str) -> T:
    if value is None:
        raise ValueError(f"Message is missing {description}")
    return value


async def download_media(bot: Bot, message: types.Message, base_dir: Path) -> str:
    """Download Telegram media and return its safe local filename."""

    file_id = None
    filename = "unknown.bin"
    logging.info("Message type=%s", message.content_type)
    if message.content_type == ContentType.PHOTO:
        photo = _require(message.photo, "photo attachment")
        if not photo:
            raise ValueError("Message photo list is empty")
        file_id = photo[-1].file_id
        filename = f"photo_{message.message_id}.jpg"
    elif message.content_type == ContentType.DOCUMENT:
        document = _require(message.document, "document attachment")
        file_id = document.file_id
        filename = document.file_name or f"doc_{message.message_id}"
    elif message.content_type == ContentType.AUDIO:
        audio = _require(message.audio, "audio attachment")
        file_id = audio.file_id
        filename = audio.file_name or f"audio_{message.message_id}.mp3"
    elif message.content_type == ContentType.VIDEO:
        video = _require(message.video, "video attachment")
        file_id = video.file_id
        filename = video.file_name or f"video_{message.message_id}.mp4"
    elif message.content_type == ContentType.VOICE:
        voice = _require(message.voice, "voice attachment")
        file_id = voice.file_id
        filename = f"voice_{message.message_id}.ogg"
    elif message.content_type == ContentType.VIDEO_NOTE:
        video_note = _require(message.video_note, "video note attachment")
        file_id = video_note.file_id
        filename = f"videonote_{message.message_id}.mp4"
    elif message.content_type == ContentType.ANIMATION:
        animation = _require(message.animation, "animation attachment")
        file_id = animation.file_id
        filename = animation.file_name or f"anim_{message.message_id}.gif"
    elif message.content_type == ContentType.STICKER:
        sticker = _require(message.sticker, "sticker attachment")
        file_id = sticker.file_id
        filename = f"sticker_{message.message_id}.webp"
    else:
        raise ValueError(f"Unsupported media type: {message.content_type}")

    telegram_file = await bot.get_file(_require(file_id, "file id"))
    file_path = _require(telegram_file.file_path, "telegram file path")
    raw_bytes = _require(
        await bot.download_file(file_path),
        "downloaded file data",
    )
    payload: bytes = raw_bytes.read()

    safe_name = sanitize_download_filename(filename)
    local_path = base_dir / safe_name
    logging.info("Saving Telegram file path=%s", local_path)
    base_dir.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(local_path, "wb") as file:
        await file.write(payload)
    return safe_name


def sanitize_download_filename(filename: str) -> str:
    return sanitize_filename(filename, fallback="download.bin")


def classify_message(message: Message) -> str:
    if message.content_type == ContentType.TEXT:
        return "only_text"
    if message.caption:
        return "text_file"
    return "only_file"


__all__ = ["classify_message", "download_media", "sanitize_download_filename"]

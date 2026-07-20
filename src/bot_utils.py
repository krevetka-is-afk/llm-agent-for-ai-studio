import logging
import os
from pathlib import Path
from typing import TypeVar, Optional

import aiofiles
from aiogram import Bot, types
from aiogram.types import ContentType, Message

from file_security import sanitize_filename

T = TypeVar("T")


def _require(value: Optional[T], description: str) -> T:
    if value is None:
        raise ValueError(f"Message is missing {description}")
    return value


async def download_media(bot: Bot, msg: types.Message, base_dir: Path) -> str:
    """Скачивает медиа‑файл из сообщения и возвращает путь к локальному файлу."""
    file_id = None
    filename = "unknown.bin"

    logging.info("Message type=%s", msg.content_type)
    if msg.content_type == ContentType.PHOTO:
        photo = _require(msg.photo, "photo attachment")
        if not photo:
            raise ValueError("Message photo list is empty")
        file_id = photo[-1].file_id
        filename = f"photo_{msg.message_id}.jpg"
    elif msg.content_type == ContentType.DOCUMENT:
        document = _require(msg.document, "document attachment")
        file_id = document.file_id
        filename = document.file_name or f"doc_{msg.message_id}"
    elif msg.content_type == ContentType.AUDIO:
        audio = _require(msg.audio, "audio attachment")
        file_id = audio.file_id
        filename = audio.file_name or f"audio_{msg.message_id}.mp3"
    elif msg.content_type == ContentType.VIDEO:
        video = _require(msg.video, "video attachment")
        file_id = video.file_id
        filename = video.file_name or f"video_{msg.message_id}.mp4"
    elif msg.content_type == ContentType.VOICE:
        voice = _require(msg.voice, "voice attachment")
        file_id = voice.file_id
        filename = f"voice_{msg.message_id}.ogg"
    elif msg.content_type == ContentType.VIDEO_NOTE:
        video_note = _require(msg.video_note, "video note attachment")
        file_id = video_note.file_id
        filename = f"videonote_{msg.message_id}.mp4"
    elif msg.content_type == ContentType.ANIMATION:
        animation = _require(msg.animation, "animation attachment")
        file_id = animation.file_id
        filename = animation.file_name or f"anim_{msg.message_id}.gif"
    elif msg.content_type == ContentType.STICKER:
        sticker = _require(msg.sticker, "sticker attachment")
        file_id = sticker.file_id
        filename = f"sticker_{msg.message_id}.webp"
    else:
        raise ValueError(f"Unsupported media type: {msg.content_type}")

    tg_file = await bot.get_file(_require(file_id, "file id"))
    file_path = _require(tg_file.file_path, "telegram file path")
    raw_bytes = _require(await bot.download_file(file_path), "downloaded file data")
    payload: bytes = raw_bytes.read()

    safe_name = sanitize_download_filename(filename)
    local_path = base_dir / safe_name
    logging.info("Saving Telegram file path=%s", local_path)
    os.makedirs(base_dir, exist_ok=True)
    async with aiofiles.open(local_path, "wb") as f:
        await f.write(payload)

    return safe_name


def sanitize_download_filename(filename: str) -> str:
    return sanitize_filename(filename, fallback="download.bin")


def classify_message(msg: Message) -> str:
    if msg.content_type == ContentType.TEXT:
        return "only_text"
    if msg.caption:
        return "text_file"
    return "only_file"

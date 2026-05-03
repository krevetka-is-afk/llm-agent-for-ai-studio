import logging
import os
from pathlib import Path

import aiofiles
from aiogram import Bot, types
from aiogram.types import ContentType, Message


async def download_media(bot: Bot, msg: types.Message, base_dir: Path) -> Path:
    """Скачивает медиа‑файл из сообщения и возвращает путь к локальному файлу."""
    file_id = None
    filename = "unknown.bin"

    logging.info(f"Message type = {msg.content_type}")
    if msg.content_type == ContentType.PHOTO:
        file_id = msg.photo[-1].file_id
        filename = f"photo_{msg.message_id}.jpg"
    elif msg.content_type == ContentType.DOCUMENT:
        file_id = msg.document.file_id
        filename = msg.document.file_name or f"doc_{msg.message_id}"
    elif msg.content_type == ContentType.AUDIO:
        file_id = msg.audio.file_id
        filename = msg.audio.file_name or f"audio_{msg.message_id}.mp3"
    elif msg.content_type == ContentType.VIDEO:
        file_id = msg.video.file_id
        filename = msg.video.file_name or f"video_{msg.message_id}.mp4"
    elif msg.content_type == ContentType.VOICE:
        file_id = msg.voice.file_id
        filename = f"voice_{msg.message_id}.ogg"
    elif msg.content_type == ContentType.VIDEO_NOTE:
        file_id = msg.video_note.file_id
        filename = f"videonote_{msg.message_id}.mp4"
    elif msg.content_type == ContentType.ANIMATION:
        file_id = msg.animation.file_id
        filename = msg.animation.file_name or f"anim_{msg.message_id}.gif"
    elif msg.content_type == ContentType.STICKER:
        file_id = msg.sticker.file_id
        filename = f"sticker_{msg.message_id}.webp"
    else:
        raise ValueError(f"Unsupported media type: {msg.content_type}")

    tg_file = await bot.get_file(file_id)
    raw_bytes = await bot.download_file(tg_file.file_path)

    safe_name = filename.replace("/", "_")
    local_path = base_dir / safe_name
    logging.info(f"Trying to save file {local_path}")
    os.makedirs(base_dir, exist_ok=True)  
    async with aiofiles.open(local_path, "wb") as f:
        await f.write(raw_bytes.read())

    return safe_name


def classify_message(msg: Message) -> str:
    if msg.content_type == ContentType.TEXT:
        return "only_text"
    if msg.caption:
        return "text_file"
    return "only_file"
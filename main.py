# -*- coding: utf-8 -*-
"""
LLM‑orchestrated Telegram bot.

Features (as of this skeleton):
* upload a file → storage (S3, local folder, etc.)
* build a vector/keyword index from stored files
* search that index
* fallback: simple Yandex video search (kept as an example “tool”)
* history / stats (re‑used from your original db helpers)

All “abilities” are expressed as **LLM‑callable functions** (OpenAI function calling).
"""

import asyncio
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command

from src.bot_utils import classify_message, download_media
from src.config import Settings
from src.context import AppContext
from src.rag_agent_server import RagServer
from src.session import get_session
from src.utils import get_streaming_response, get_user_client

logging.basicConfig(level=logging.INFO, filename='app.log',
                    format='%(asctime)s – %(name)s – %(levelname)s – %(message)s')


BOT_TOKEN = os.getenv("BOT_TOKEN")


router = Router()
dp = Dispatcher()
dp.include_router(router)
bot = Bot(token=BOT_TOKEN)


@dataclass
class UserSecrets:
    api_token: str | None = None
    folder_id: str | None = None
users_db = defaultdict(UserSecrets)

@router.message(Command(commands=["start"]))
async def cmd_start(message: types.Message):
    await message.reply(
        "Привет! Я — бот‑помощник с функциями LLM‑управления.\n"
        "Отправьте любой запрос, а я решу, какая из моих возможностей вам нужна.\n"
        "Перед началом работы отправь свой api-token и folder-id"
        "Доступные команды:\n"
        "/help    — это сообщение подсказка\n"
        "/reset   - сбор всего предыдущего взаимодействия\n"
        "/set_api_token - сохранение своего токена\n"
        "/set_folder_id - сохранение своего folder_id"
    )

@router.message(Command(commands=["help"]))
async def cmd_help(message: types.Message):
    await message.reply(
        "/help    — это сообщение подсказка\n"
        "/reset   - сбор всего предыдущего взаимодействия\n"
        "/set_api_token - сохранение своего токена\n"
        "/set_folder_id - сохранение своего folder_id\n"
        "Любой свободный текст будет обработан LLM‑моделью, которая может вызвать "
        "одну из её функций (загрузка, индексация, поиск, кино‑поиск)."
    )

@router.message(Command(commands=["reset"]))
async def cmd_session_restart(message: types.Message):
    user_id = str(message.from_user.id)
    session = get_session(user_id)
    await session.clear_session()
    await message.reply(f"Session {user_id} cleared")

@router.message(Command(commands=["set_api_token"]))
async def cmd_set_token(message: types.Message):
    user_id = str(message.from_user.id)
    users_db[user_id].api_token = message.text.strip().split(' ')[-1]
    logging.info(f"Saved api token = '{message.text.strip().split(' ')[-1]}'")
    await message.reply("Api token saved")

@router.message(Command(commands=["set_folder_id"]))
async def cmd_set_folder_id(message: types.Message):
    user_id = str(message.from_user.id)
    users_db[user_id].folder_id = message.text.strip().split(' ')[-1]
    logging.info(f"Saved folder id = '{message.text.strip().split(' ')[-1]}'")
    await message.reply("Folder id saved")

@router.message()
async def universal_handler(message: types.Message):
    user_id = str(message.from_user.id)

    user_secrets = users_db[user_id]
    if user_secrets.api_token is None:
        await message.reply("Before asking model set api token key by /set_api_token command")
        return
    if user_secrets.folder_id is None:
        await message.reply("Before asking model set folder id key by /set_folder_id command")
        return

    settings = Settings.load_settings()

    base_dir = 'files_to_upload'
    base_dir = Path(base_dir).resolve() / user_id

    kind = classify_message(message)
    if kind == "only_file":
        filename = await download_media(bot, message, base_dir)
        combined_prompt = f"Uploaded file by user: {filename}\n"
    elif kind == "text_file":
        filename = await download_media(bot, message, base_dir)
        user_text = message.caption or ""
        combined_prompt = f"Uploaded file by user: {filename} with request request: {user_text}\n"
    else:
        user_text = message.text or ""
        combined_prompt = f"User request: {user_text}\n"

    client = get_user_client(user_secrets.api_token, user_secrets.folder_id, settings)
    rag_server = RagServer(settings, client)
    context = AppContext(
        user_id, 
        client=client,
        base_dir=base_dir,
        is_done=False,
    )

    logging.info(f"Call llm with prompt {combined_prompt}")
    output = await get_streaming_response(rag_server, combined_prompt, context=context)
    logging.info(f"{output=}")
    if output.strip() == "":
        await message.answer("Empty output")
    else:
        await message.answer(output)

async def main() -> None:
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

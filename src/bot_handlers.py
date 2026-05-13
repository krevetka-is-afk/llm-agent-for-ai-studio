import logging
from pathlib import Path
from aiogram import Bot
from aiogram import Router, types
from aiogram.filters import Command

from message_service import MessageService
from session import get_session
from context import UserSecretsStore
from bot_utils import classify_message, download_media
from config import Settings


def create_router(
    settings: Settings,
    bot: Bot,
    secrets_store: UserSecretsStore,
    message_service: MessageService,
) -> Router:
    router = Router()

    @router.message(Command(commands=["start"]))
    async def cmd_start(message: types.Message):
        await message.reply(
            message_service.welcome_message + "\n" + message_service.render_help_msg()
        )

    @router.message(Command(commands=["help"]))
    async def cmd_help(message: types.Message):
        await message.reply(message_service.render_help_msg())

    @router.message(Command(commands=["reset"]))
    async def cmd_session_restart(message: types.Message):
        user_id = str(_require_from_user(message).id)
        session = get_session(user_id, settings.db_path)
        await session.clear_session()
        await message.reply(f"Session {user_id} cleared")

    @router.message(Command(commands=["set_api_token"]))
    async def cmd_set_token(message: types.Message):
        user_id = str(_require_from_user(message).id)
        api_token = _last_command_argument(message)
        if api_token is None:
            await message.reply(
                message_service.render_command_usage_msg(
                    "/set_api_token",
                    "Команда вызвана без аргументов.",
                )
            )
            return
        secrets_store.set_api_token(user_id, api_token)
        logging.info(f"Saved api token for user_id={user_id}")
        await message.reply("Api token saved")

    @router.message(Command(commands=["set_folder_id"]))
    async def cmd_set_folder_id(message: types.Message):
        user_id = str(_require_from_user(message).id)
        folder_id = _last_command_argument(message)
        if folder_id is None:
            await message.reply(
                message_service.render_command_usage_msg(
                    "/set_folder_id",
                    "Команда вызвана без аргументов.",
                )
            )
            return
        secrets_store.set_folder_id(user_id, folder_id)
        logging.info(f"Saved folder id for user_id={user_id}")
        await message.reply("Folder id saved")

    @router.message()
    async def universal_handler(message: types.Message) -> None:
        user_id = str(_require_from_user(message).id)
        user_secrets = secrets_store.get(user_id)

        if user_secrets.api_token is None:
            await message.reply(
                message_service.render_command_usage_msg(
                    "/set_api_token",
                    "Перед запросом к модели сначала сохраните API token.",
                )
            )
            return
        if user_secrets.folder_id is None:
            await message.reply(
                message_service.render_command_usage_msg(
                    "/set_folder_id",
                    "Перед запросом к модели сначала сохраните folder id.",
                )
            )
            return

        base_dir = Path(settings.upload_base_dir).resolve() / user_id

        filename = None
        kind = classify_message(message)
        if kind in {"only_file", "text_file"}:
            filename = await download_media(bot, message, base_dir)

        combined_prompt = message_service.build_prompt(
            text=message.text, caption=message.caption, file_name=filename
        )

        output = await message_service.generate_response(
            user_id=user_id,
            api_token=user_secrets.api_token,
            folder_id=user_secrets.folder_id,
            combined_prompt=combined_prompt,
            base_dir=base_dir,
        )

        if output.strip() == "":
            await message.answer("Empty output")
        else:
            await message.answer(output)

    return router


def _require_from_user(message: types.Message) -> types.User:
    if message.from_user is None:
        raise ValueError("Telegram message does not have a sender")
    return message.from_user


def _require_message_text(message: types.Message) -> str:
    if message.text is None:
        raise ValueError("Telegram command message does not have text")
    return message.text


def _last_command_argument(message: types.Message) -> str | None:
    text = _require_message_text(message).strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        return None
    return parts[1].strip()

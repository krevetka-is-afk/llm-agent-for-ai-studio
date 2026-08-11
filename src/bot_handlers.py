import logging
from pathlib import Path
from typing import Protocol

from aiogram import Bot
from aiogram import Router, types
from aiogram.filters import Command

from ai_studio_agent_builder.config import PathConfig
from ai_studio_agent_builder.infrastructure.persistence.telegram_user_store import (
    UserStore,
)
from ai_interaction_service import AIInteractionService, Attachment, InteractionRequest
from bot_utils import classify_message, download_media
from context import AIStudioCredentials
from message_service import MessageService
from telegram_flow import PerUserRequestGate


class TelegramMessageDeleter(Protocol):
    async def delete_message(self, chat_id: int, message_id: int) -> bool: ...


def create_router(
    bot: Bot,
    ai_service: AIInteractionService,
    paths: PathConfig,
    user_store: UserStore,
) -> Router:
    router = Router()
    handlers = TelegramHandlers(bot, ai_service, paths, user_store)
    router.message.register(handlers.cmd_start, Command(commands=["start"]))
    router.message.register(handlers.cmd_help, Command(commands=["help"]))
    router.message.register(handlers.cmd_session_restart, Command(commands=["reset"]))
    router.message.register(
        handlers.cmd_clear_credentials, Command(commands=["clear_credentials"])
    )
    router.message.register(handlers.cmd_set_token, Command(commands=["set_api_token"]))
    router.message.register(
        handlers.cmd_set_folder_id, Command(commands=["set_folder_id"])
    )
    router.message.register(handlers.universal_handler)
    return router


class TelegramHandlers:
    def __init__(
        self,
        bot: Bot,
        ai_service: AIInteractionService,
        paths: PathConfig,
        user_store: UserStore,
    ) -> None:
        self._bot = bot
        self._ai_service = ai_service
        self._paths = paths
        self._user_store = user_store
        self._message_service = MessageService()
        self._request_gate = PerUserRequestGate()

    async def cmd_start(self, message: types.Message) -> None:
        await message.reply(
            self._message_service.welcome_message
            + "\n"
            + self._message_service.render_help_msg()
        )

    async def cmd_help(self, message: types.Message) -> None:
        await message.reply(self._message_service.render_help_msg())

    async def cmd_session_restart(self, message: types.Message) -> None:
        user_id = str(_require_from_user(message).id)
        async with self._request_gate.hold(user_id):
            await self._ai_service.reset_conversation(user_id)
            self._user_store.get_state(user_id).reset_state()
        await message.reply(f"Session {user_id} cleared")

    async def cmd_clear_credentials(self, message: types.Message) -> None:
        if not _is_private_chat(message):
            await message.reply(
                "Для безопасности удалить сохранённые данные можно только в личном чате."
            )
            return
        user_id = str(_require_from_user(message).id)
        async with self._request_gate.hold(user_id):
            message_ids = self._user_store.clear_credentials(user_id)
            await self._ai_service.reset_conversation(user_id)
            deleted = await _delete_secret_messages(
                self._bot, message.chat.id, message_ids
            )
        if deleted:
            await message.reply("API-ключ, folder ID и история сессии удалены.")
        else:
            await message.reply(
                "Данные подключения удалены. Не удалось удалить одно из сообщений — "
                "удалите его вручную."
            )

    async def cmd_set_token(self, message: types.Message) -> None:
        if not _is_private_chat(message):
            await message.reply(
                "Для безопасности API-ключ можно отправлять только в личном чате с ботом."
            )
            return
        user_id = str(_require_from_user(message).id)
        api_token = _last_command_argument(message)
        if api_token is None:
            await message.reply(
                self._message_service.render_command_usage_msg(
                    "/set_api_token",
                    "Команда вызвана без аргументов.",
                )
            )
            return
        async with self._request_gate.hold(user_id):
            self._user_store.set_pending_api_token(
                user_id, api_token, message.message_id
            )
            await _validate_pending_connection(
                message,
                user_id,
                self._user_store,
                self._ai_service,
                self._bot,
            )

    async def cmd_set_folder_id(self, message: types.Message) -> None:
        if not _is_private_chat(message):
            await message.reply(
                "Для безопасности folder ID можно отправлять только в личном чате с ботом."
            )
            return
        user_id = str(_require_from_user(message).id)
        folder_id = _last_command_argument(message)
        if folder_id is None:
            await message.reply(
                self._message_service.render_command_usage_msg(
                    "/set_folder_id",
                    "Команда вызвана без аргументов.",
                )
            )
            return
        async with self._request_gate.hold(user_id):
            self._user_store.set_pending_folder_id(
                user_id, folder_id, message.message_id
            )
            await _validate_pending_connection(
                message,
                user_id,
                self._user_store,
                self._ai_service,
                self._bot,
            )

    async def universal_handler(self, message: types.Message) -> None:
        user_id = str(_require_from_user(message).id)
        async with self._request_gate.hold(user_id):
            conv_state = self._user_store.get_state(user_id)

            credentials = await _resolve_credentials(user_id, self._user_store, message)
            if credentials is None:
                return

            base_dir = Path(self._paths.uploaded_files_dir).resolve() / user_id

            filename = None
            kind = classify_message(message)
            if kind in {"only_file", "text_file"}:
                filename = await download_media(self._bot, message, base_dir)

            attachment = (
                Attachment(filename=filename, caption=message.caption)
                if filename is not None
                else None
            )
            result = await self._ai_service.interact(
                InteractionRequest(
                    user_id=user_id,
                    request_id=f"telegram-{message.chat.id}-{message.message_id}",
                    text=message.text,
                    credentials=credentials,
                    conversation_state=conv_state,
                    user_files_dir=base_dir,
                    attachment=attachment,
                )
            )

            if result.text.strip() == "":
                await message.answer("Empty output")
            else:
                await message.answer(result.text)


async def _validate_pending_connection(
    message: types.Message,
    user_id: str,
    user_store: UserStore,
    ai_service: AIInteractionService,
    bot: Bot,
) -> None:
    credentials = user_store.get_pending_credentials(user_id)
    if credentials is None:
        await message.reply(
            "Данные сохранены временно. Отправьте второе значение для проверки подключения."
        )
        return
    try:
        await ai_service.validate_connection(credentials)
    except Exception:
        logging.exception(
            "AI Studio connection validation failed for user_id=%s", user_id
        )
        await message.reply(
            "Не удалось проверить подключение. Проверьте API-ключ и folder ID."
        )
        return

    message_ids = user_store.activate_pending_credentials(user_id)
    deleted = await _delete_secret_messages(bot, message.chat.id, message_ids)
    if deleted:
        await message.reply(
            "Подключение проверено. Сообщения с ключом и folder ID удалены."
        )
    else:
        await message.reply(
            "Подключение проверено. Не удалось удалить одно из сообщений — удалите их вручную."
        )


async def _delete_secret_messages(
    bot: TelegramMessageDeleter, chat_id: int, message_ids: tuple[int, ...]
) -> bool:
    try:
        for message_id in message_ids:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        logging.exception(
            "Could not delete secret Telegram message chat_id=%s message_ids=%s",
            chat_id,
            message_ids,
        )
        return False
    return True


async def _resolve_credentials(
    user_id: str,
    user_store: UserStore,
    message: types.Message,
) -> AIStudioCredentials | None:
    manual = user_store.get(user_id)
    if manual.api_token is None:
        await message.reply(
            MessageService.render_command_usage_msg(
                "/set_api_token", "Сначала сохраните API-ключ."
            )
        )
        return None
    if manual.folder_id is None:
        await message.reply(
            MessageService.render_command_usage_msg(
                "/set_folder_id", "Перед запросом сначала сохраните folder id."
            )
        )
        return None
    return AIStudioCredentials(api_key=manual.api_token, folder_id=manual.folder_id)


def _require_from_user(message: types.Message) -> types.User:
    if message.from_user is None:
        raise ValueError("Telegram message does not have a sender")
    return message.from_user


def _is_private_chat(message: types.Message) -> bool:
    return message.chat.type == "private"


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

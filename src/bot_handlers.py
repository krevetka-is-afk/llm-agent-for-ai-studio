import logging
from pathlib import Path
from aiogram import Bot, F
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from message_service import MessageService
from session import get_session
from context import UserCredentials, UserStore
from bot_utils import classify_message, download_media
from config import SessionDBConfig, PathConfig
from experimental.oauth.client import (
    GatewayClientNotConnected,
    GatewayClientReauthorizationRequired,
    GatewayClientUnavailable,
    GatewayFolder,
    OAuthGatewayClient,
)


def create_router(
    bot: Bot,
    message_service: MessageService,
    session_db: SessionDBConfig,
    paths: PathConfig,
    user_store: UserStore,
    oauth_gateway: OAuthGatewayClient | None = None,
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
        session = get_session(user_id, session_db.path)
        await session.clear_session()
        await message.reply(f"Session {user_id} cleared")

    @router.message(Command(commands=["connect_yc"]))
    async def cmd_connect_yc(message: types.Message) -> None:
        if oauth_gateway is None:
            await message.reply("OAuth Yandex Cloud не настроен на стороне бота.")
            return
        user_id = str(_require_from_user(message).id)
        try:
            url = await oauth_gateway.begin_authorization(user_id)
        except GatewayClientUnavailable:
            await message.reply("OAuth Gateway временно недоступен.")
            return
        user_store.clear_folder_id(user_id)
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Подключить Yandex Cloud", url=url)
        await message.reply(
            "Откройте Yandex Cloud, войдите в аккаунт и подтвердите доступ.",
            reply_markup=keyboard.as_markup(),
        )

    @router.message(Command(commands=["yc_status"]))
    async def cmd_yc_status(message: types.Message) -> None:
        if oauth_gateway is None:
            await message.reply("OAuth Yandex Cloud не настроен на стороне бота.")
            return
        user_id = str(_require_from_user(message).id)
        try:
            connected = await oauth_gateway.status(user_id)
        except GatewayClientUnavailable:
            await message.reply("OAuth Gateway временно недоступен.")
            return
        folder_id = user_store.get(user_id).folder_id
        if not connected:
            await message.reply("Yandex Cloud не подключен. Используйте /connect_yc.")
        elif folder_id is None:
            await message.reply("Yandex Cloud подключен. Выберите папку: /yc_folders.")
        else:
            await message.reply(f"Yandex Cloud подключен. Папка: <code>{folder_id}</code>")

    @router.message(Command(commands=["yc_folders"]))
    async def cmd_yc_folders(message: types.Message) -> None:
        if oauth_gateway is None:
            await message.reply("OAuth Yandex Cloud не настроен на стороне бота.")
            return
        user_id = str(_require_from_user(message).id)
        try:
            folders = await oauth_gateway.list_folders(user_id)
        except GatewayClientNotConnected:
            await message.reply("Сначала подключите Yandex Cloud: /connect_yc.")
            return
        except GatewayClientReauthorizationRequired:
            await message.reply("Подключение истекло. Подключите Yandex Cloud заново: /connect_yc.")
            return
        except GatewayClientUnavailable:
            logging.exception("Could not list Yandex Cloud folders for user_id=%s", user_id)
            await message.reply("Не удалось получить список папок Yandex Cloud.")
            return
        await _reply_with_folders(message, folders)

    @router.callback_query(F.data.startswith("yc_folder:"))
    async def select_yc_folder(callback: types.CallbackQuery) -> None:
        if oauth_gateway is None or callback.data is None:
            await callback.answer("OAuth Yandex Cloud не настроен.", show_alert=True)
            return
        if callback.from_user is None:
            await callback.answer("Не удалось определить пользователя.", show_alert=True)
            return
        folder_id = callback.data.removeprefix("yc_folder:")
        try:
            await oauth_gateway.validate_folder(str(callback.from_user.id), folder_id)
        except (GatewayClientNotConnected, GatewayClientReauthorizationRequired):
            await callback.answer("Подключение истекло. Используйте /connect_yc.", show_alert=True)
            return
        except GatewayClientUnavailable:
            await callback.answer("Папка недоступна. Обновите список: /yc_folders.", show_alert=True)
            return
        user_store.set_folder_id(str(callback.from_user.id), folder_id)
        await callback.answer("Папка выбрана")
        if isinstance(callback.message, types.Message):
            await callback.message.edit_text("Папка Yandex Cloud выбрана. Можно отправлять запросы.")

    @router.message(Command(commands=["disconnect_yc"]))
    async def cmd_disconnect_yc(message: types.Message) -> None:
        if oauth_gateway is None:
            await message.reply("OAuth Yandex Cloud не настроен на стороне бота.")
            return
        user_id = str(_require_from_user(message).id)
        try:
            await oauth_gateway.disconnect(user_id)
        except GatewayClientUnavailable:
            await message.reply("OAuth Gateway временно недоступен. Подключение не изменено.")
            return
        user_store.clear_folder_id(user_id)
        await message.reply("Yandex Cloud отключен. Локальные токены удалены.")

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
        user_store.set_api_token(user_id, api_token)
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
        user_store.set_folder_id(user_id, folder_id)
        logging.info(f"Saved folder id for user_id={user_id}")
        await message.reply("Folder id saved")

    @router.message()
    async def universal_handler(message: types.Message) -> None:
        user_id = str(_require_from_user(message).id)
        conv_state = user_store.get_state(user_id)

        credentials = await _resolve_credentials(user_id, user_store, oauth_gateway, message)
        if credentials is None:
            return

        base_dir = Path(paths.uploaded_files_dir).resolve() / user_id

        filename = None
        kind = classify_message(message)
        if kind in {"only_file", "text_file"}:
            filename = await download_media(bot, message, base_dir)

        combined_prompt = message_service.build_prompt(
            text=message.text, caption=message.caption, file_name=filename
        )

        output = await message_service.generate_response(
            user_id=user_id,
            access_token=credentials.access_token,
            folder_id=credentials.folder_id,
            conversation_state=conv_state,
            combined_prompt=combined_prompt,
            base_dir=base_dir,
        )

        if output.strip() == "":
            await message.answer("Empty output")
        else:
            await message.answer(output)

    return router


def build_folder_keyboard(folders: tuple[GatewayFolder, ...]) -> types.InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    for folder in folders:
        keyboard.button(text=folder.label[:64], callback_data=f"yc_folder:{folder.id}")
    keyboard.adjust(1)
    return keyboard.as_markup()


async def _reply_with_folders(
    message: types.Message, folders: tuple[GatewayFolder, ...]
) -> None:
    if not folders:
        await message.reply(
            "Доступных папок не найдено. Проверьте права доступа в Yandex Cloud."
        )
        return
    await message.reply(
        "Выберите папку для списания расходов:", reply_markup=build_folder_keyboard(folders)
    )


async def _resolve_credentials(
    user_id: str,
    user_store: UserStore,
    oauth_gateway: OAuthGatewayClient | None,
    message: types.Message,
) -> UserCredentials | None:
    if oauth_gateway is not None:
        try:
            if not await oauth_gateway.status(user_id):
                raise GatewayClientNotConnected("Yandex Cloud is not connected")
            folder_id = user_store.get(user_id).folder_id
            if folder_id is None:
                await message.reply("Выберите папку Yandex Cloud: /yc_folders.")
                return None
            return await oauth_gateway.get_credentials(user_id, folder_id)
        except GatewayClientNotConnected:
            pass
        except GatewayClientReauthorizationRequired:
            await message.reply("Подключение Yandex Cloud истекло. Используйте /connect_yc.")
            return None
        except GatewayClientUnavailable:
            logging.exception("Could not resolve Yandex Cloud credentials for user_id=%s", user_id)
            await message.reply("Не удалось получить доступ к Yandex Cloud. Повторите /connect_yc.")
            return None

    manual = user_store.get(user_id)
    if manual.api_token is None:
        await message.reply(
            MessageService.render_command_usage_msg(
                "/set_api_token", "Подключите Yandex Cloud: /connect_yc."
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
    return UserCredentials(access_token=manual.api_token, folder_id=manual.folder_id)


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

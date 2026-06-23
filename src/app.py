from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from message_service import MessageService
from config import Settings
from bot_handlers import create_router
from context import UserSecretsStore


def create_app(settings: Settings) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    secrets_store = UserSecretsStore(settings.user_secrets_path)
    message_service = MessageService(settings)

    router = create_router(
        settings=settings,
        bot=bot,
        secrets_store=secrets_store,
        message_service=message_service,
    )

    dp.include_router(router)
    return bot, dp

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.message_service import MessageService
from src.config import Settings
from src.bot_handlers import create_router
from src.context import UserSecretsStore


def create_app(settings: Settings) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    secrets_store = UserSecretsStore()
    message_service = MessageService(settings)

    router = create_router(
        settings=settings,
        bot=bot,
        secrets_store=secrets_store,
        message_service=message_service,
    )

    dp.include_router(router)
    return bot, dp

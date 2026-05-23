from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from message_service import MessageService
from config import AppConfig
from bot_handlers import create_router
from context import UserSecretsStore


def create_app(config: AppConfig) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=config.bot.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    secrets_store = UserSecretsStore()
    message_service = MessageService(config)

    router = create_router(
        bot=bot,
        secrets_store=secrets_store,
        message_service=message_service,
        path_config=config.paths,
    )

    dp.include_router(router)
    return bot, dp

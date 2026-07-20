import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from ai_interaction_service import AIInteractionService
from config import load_config, AppConfig
from bot_handlers import create_router
from context import UserStore
from logging_config import configure_console_logging
from telegram_session import HttpProxyTelegramSession


def create_app(config: AppConfig) -> tuple[Bot, Dispatcher]:
    session = (
        HttpProxyTelegramSession(config.bot.telegram_proxy_url)
        if config.bot.telegram_proxy_url is not None
        else None
    )
    bot = Bot(
        token=config.bot.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = Dispatcher()

    users_store = UserStore()
    ai_service = AIInteractionService(config.ai_service)

    router = create_router(
        bot=bot,
        ai_service=ai_service,
        paths=config.ai_service.paths,
        user_store=users_store,
    )

    dp.include_router(router)
    return bot, dp


async def main() -> None:
    logging.getLogger(__name__).info("Main started")
    config: AppConfig = load_config()
    bot, dp = create_app(config)
    await dp.start_polling(bot)


if __name__ == "__main__":
    configure_console_logging()
    asyncio.run(main())

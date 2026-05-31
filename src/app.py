import logging
import sys
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from message_service import MessageService
from config import load_config, AppConfig
from bot_handlers import create_router
from context import UserStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)


def create_app(config: AppConfig) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=config.bot.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    users_store = UserStore()
    message_service = MessageService(config)

    router = create_router(
        bot=bot,
        message_service=message_service,
        session_db=config.session_db_config,
        paths=config.paths,
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
    asyncio.run(main())

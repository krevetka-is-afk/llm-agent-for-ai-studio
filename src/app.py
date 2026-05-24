import logging
import sys
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from message_service import MessageService
from config import Settings
from bot_handlers import create_router
from context import UserStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)


def create_app(settings: Settings) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    users_store = UserStore()
    message_service = MessageService(settings)

    router = create_router(
        settings=settings,
        bot=bot,
        user_store=users_store,
        message_service=message_service,
    )

    dp.include_router(router)
    return bot, dp


async def main() -> None:
    logging.getLogger(__name__).info("Main started")
    settings = Settings.load_settings()
    bot, dp = create_app(settings)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

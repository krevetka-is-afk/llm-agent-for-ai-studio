import logging
import sys
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from message_service import MessageService
from config import load_config, AppConfig
from bot_handlers import create_router
from context import UserSecretsStore
from miniapp_server import create_miniapp_web_app, start_miniapp_server
from yc_connect import ConnectionStateStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)


def create_app(
    config: AppConfig,
    *,
    users_store: UserSecretsStore | None = None,
    connection_states: ConnectionStateStore | None = None,
) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=config.bot.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    users_store = users_store or UserSecretsStore(config.auth)
    connection_states = connection_states or ConnectionStateStore(
        ttl_seconds=config.mini_app.connect_state_ttl_seconds
    )
    message_service = MessageService(config)

    router = create_router(
        bot=bot,
        message_service=message_service,
        session_db=config.session_db_config,
        paths=config.paths,
        user_store=users_store,
        mini_app=config.mini_app,
        connection_states=connection_states,
    )

    dp.include_router(router)
    return bot, dp


async def main() -> None:
    logging.getLogger(__name__).info("Main started")
    config: AppConfig = load_config()
    users_store = UserSecretsStore(config.auth)
    connection_states = ConnectionStateStore(
        ttl_seconds=config.mini_app.connect_state_ttl_seconds
    )
    bot, dp = create_app(
        config,
        users_store=users_store,
        connection_states=connection_states,
    )
    web_app = create_miniapp_web_app(
        bot=bot,
        config=config,
        user_store=users_store,
        state_store=connection_states,
    )
    web_runner: web.AppRunner | None = None
    try:
        web_runner = await start_miniapp_server(
            web_app,
            host=config.mini_app.host,
            port=config.mini_app.port,
        )
        await dp.start_polling(bot)
    finally:
        if web_runner is not None:
            await web_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

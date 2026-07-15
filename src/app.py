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
from experimental.oauth.client import OAuthGatewayClient
from experimental.oauth.config import load_oauth_gateway_client_config
from telegram_session import HttpProxyTelegramSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)


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
    message_service = MessageService(config)
    oauth_gateway_config = load_oauth_gateway_client_config()
    oauth_gateway = (
        OAuthGatewayClient(oauth_gateway_config)
        if oauth_gateway_config is not None
        else None
    )

    router = create_router(
        bot=bot,
        message_service=message_service,
        session_db=config.session_db_config,
        paths=config.paths,
        user_store=users_store,
        oauth_gateway=oauth_gateway,
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

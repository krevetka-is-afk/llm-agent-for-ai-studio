"""Compatibility constructor for packaged Telegram handlers."""

from aiogram import Bot, Router

from ai_studio_agent_builder.application.interaction import AIInteraction
from ai_studio_agent_builder.application.settings import PathConfig
from ai_studio_agent_builder.presentation.telegram.handlers import (
    StoredCredentials,
    TelegramHandlers as PackagedTelegramHandlers,
    TelegramMessageDeleter,
    TelegramUserStore,
    _delete_secret_messages,
    create_router as create_packaged_router,
)


class TelegramHandlers(PackagedTelegramHandlers):
    def __init__(
        self,
        bot: Bot,
        ai_service: AIInteraction,
        paths: PathConfig,
        user_store: TelegramUserStore,
    ) -> None:
        del paths
        super().__init__(bot, ai_service, user_store)


def create_router(
    bot: Bot,
    ai_service: AIInteraction,
    paths: PathConfig,
    user_store: TelegramUserStore,
) -> Router:
    del paths
    return create_packaged_router(bot, ai_service, user_store)


__all__ = [
    "_delete_secret_messages",
    "StoredCredentials",
    "TelegramHandlers",
    "TelegramMessageDeleter",
    "TelegramUserStore",
    "create_router",
]

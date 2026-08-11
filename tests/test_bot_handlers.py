import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from aiogram import Bot

from ai_studio_agent_builder.config import PathConfig
from ai_interaction_service import AIInteractionService
from bot_handlers import create_router
from context import UserStore


class FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        self.deleted.append((chat_id, message_id))
        return True


class FakeAIService:
    def __init__(self) -> None:
        self.reset_users: list[str] = []

    async def reset_conversation(self, user_id: str) -> None:
        self.reset_users.append(user_id)


class FakeMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=42)
        self.chat = SimpleNamespace(id=7, type="private")
        self.replies: list[str] = []

    async def reply(self, text: str) -> None:
        self.replies.append(text)


def test_clear_credentials_router_command_clears_store_and_secret_messages() -> None:
    bot = FakeBot()
    ai_service = FakeAIService()
    store = UserStore()
    store.set_pending_api_token("42", "secret", message_id=10)
    store.set_pending_folder_id("42", "folder", message_id=11)
    store.activate_pending_credentials("42")
    store.set_pending_api_token("42", "replacement", message_id=12)
    router = create_router(
        bot=cast(Bot, bot),
        ai_service=cast(AIInteractionService, ai_service),
        paths=PathConfig(uploaded_files_dir=Path("uploads")),
        user_store=store,
    )
    callback = cast(
        Callable[[Any], Coroutine[Any, Any, None]],
        next(
            handler.callback
            for handler in router.message.handlers
            if getattr(handler.callback, "__name__", None) == "cmd_clear_credentials"
        ),
    )
    message = FakeMessage()

    asyncio.run(callback(message))

    assert store.get("42").api_token is None
    assert store.get("42").folder_id is None
    assert bot.deleted == [(7, 12)]
    assert ai_service.reset_users == ["42"]
    assert message.replies == ["API-ключ, folder ID и история сессии удалены."]

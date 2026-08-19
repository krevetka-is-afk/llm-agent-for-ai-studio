"""Yandex AI Studio credential validation adapter."""

import asyncio
from collections.abc import Callable
from typing import Any

from openai import OpenAIError

from ai_studio_agent_builder.application.dto import AIStudioCredentials
from ai_studio_agent_builder.application.errors import AIStudioRequestError


ClientFactory = Callable[[AIStudioCredentials], Any]


class YandexConnectionValidator:
    def __init__(self, client_factory: ClientFactory, *, model_name: str) -> None:
        self._client_factory = client_factory
        self._model_name = model_name

    async def validate(self, credentials: AIStudioCredentials) -> None:
        client = self._client_factory(credentials)
        try:
            await asyncio.to_thread(
                client.responses.create,
                model=f"gpt://{credentials.folder_id}/{self._model_name}",
                input="Ответьте ровно: OK",
                max_output_tokens=2,
            )
        except OpenAIError as exc:
            raise AIStudioRequestError("AI Studio request failed") from exc


__all__ = ["YandexConnectionValidator"]

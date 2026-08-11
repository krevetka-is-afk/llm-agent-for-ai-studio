"""Application boundary for validating provider credentials."""

from typing import Protocol

from ai_studio_agent_builder.application.dto import AIStudioCredentials


class ConnectionValidator(Protocol):
    async def validate(self, credentials: AIStudioCredentials) -> None: ...


__all__ = ["ConnectionValidator"]

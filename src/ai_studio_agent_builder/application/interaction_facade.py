"""Facade matching the presentation-facing AI interaction contract."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_studio_agent_builder.application.builder_service import (
    BuilderConversationService,
)
from ai_studio_agent_builder.application.dto import AIStudioCredentials
from ai_studio_agent_builder.application.file_lifecycle import ConversationFileService
from ai_studio_agent_builder.application.interaction import (
    AgentTestRequest,
    AgentTestResult,
    Attachment,
    InteractionRequest,
    InteractionResult,
)
from ai_studio_agent_builder.application.ports.connection import ConnectionValidator
from ai_studio_agent_builder.application.preview_service import AgentPreviewService
from ai_studio_agent_builder.domain.runtime import ExecutableAgentConfig


@dataclass(frozen=True)
class AIInteractionComponents:
    builder: BuilderConversationService
    preview: AgentPreviewService
    files: ConversationFileService
    connection_validator: ConnectionValidator


class AIInteractionService:
    def __init__(self, components: AIInteractionComponents) -> None:
        self._components = components

    def user_files_dir(self, user_id: str) -> Path:
        return self._components.files.user_files_dir(user_id)

    def save_attachment(
        self,
        user_id: str,
        original_filename: str,
        content: bytes,
        caption: str | None = None,
    ) -> Attachment:
        return self._components.files.save_attachment(
            user_id,
            original_filename,
            content,
            caption=caption,
        )

    async def validate_connection(self, credentials: AIStudioCredentials) -> None:
        await self._components.connection_validator.validate(credentials)

    async def interact(self, request: InteractionRequest) -> InteractionResult:
        return await self._components.builder.interact(request)

    async def reset_conversation(self, user_id: str) -> None:
        await self._components.files.reset_conversation(user_id)

    def prepare_agent_runtime(
        self,
        specification_record: Mapping[str, Any],
    ) -> ExecutableAgentConfig:
        return self._components.preview.prepare_agent_runtime(specification_record)

    async def test_agent_specification(
        self,
        request: AgentTestRequest,
    ) -> AgentTestResult:
        return await self._components.preview.test_agent_specification(request)


__all__ = ["AIInteractionComponents", "AIInteractionService"]

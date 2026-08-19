"""Application-owned boundary for running an Agent Builder conversation turn."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ai_studio_agent_builder.application.builder_state import ConversationState
from ai_studio_agent_builder.application.dto import AIStudioCredentials
from ai_studio_agent_builder.application.interaction import Attachment
from ai_studio_agent_builder.domain.routing import ConversationOptions


@dataclass(frozen=True)
class BuilderRunRequest:
    user_id: str
    request_id: str
    text: str | None
    credentials: AIStudioCredentials
    conversation_state: ConversationState
    user_files_dir: Path
    attachments: tuple[Attachment, ...] = ()


@dataclass(frozen=True)
class BuilderRunOutcome:
    text: str
    parts: tuple[dict[str, Any], ...]
    selected_agent: ConversationOptions
    responded_by: ConversationOptions
    next_state: ConversationOptions


class BuilderRunPort(Protocol):
    """Execute one builder turn against a caller-owned working state."""

    async def run(self, request: BuilderRunRequest) -> BuilderRunOutcome: ...


__all__ = ["BuilderRunOutcome", "BuilderRunPort", "BuilderRunRequest"]

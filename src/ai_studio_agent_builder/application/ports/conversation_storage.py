"""Application boundaries for conversation-scoped files and sessions."""

from pathlib import Path
from typing import Protocol

from ai_studio_agent_builder.application.interaction import Attachment


class AttachmentReader(Protocol):
    def read_text(self, base_dir: Path, filename: str) -> str: ...


class AttachmentStore(AttachmentReader, Protocol):
    def directory_for(self, user_id: str) -> Path: ...

    def save(
        self,
        user_id: str,
        original_filename: str,
        content: bytes,
        caption: str | None = None,
    ) -> Attachment: ...

    async def clear(self, user_id: str) -> None: ...


class ConversationSessionStore(Protocol):
    async def clear(self, user_id: str) -> None: ...


__all__ = ["AttachmentReader", "AttachmentStore", "ConversationSessionStore"]

"""Application ownership of conversation file and session cleanup."""

from pathlib import Path

from ai_studio_agent_builder.application.interaction import Attachment
from ai_studio_agent_builder.application.ports.conversation_storage import (
    AttachmentStore,
    ConversationSessionStore,
)


class ConversationFileService:
    def __init__(
        self,
        attachment_store: AttachmentStore,
        session_store: ConversationSessionStore,
    ) -> None:
        self._attachment_store = attachment_store
        self._session_store = session_store

    def user_files_dir(self, user_id: str) -> Path:
        return self._attachment_store.directory_for(user_id)

    def save_attachment(
        self,
        user_id: str,
        original_filename: str,
        content: bytes,
        caption: str | None = None,
    ) -> Attachment:
        return self._attachment_store.save(
            user_id,
            original_filename,
            content,
            caption=caption,
        )

    async def reset_conversation(self, user_id: str) -> None:
        await self._session_store.clear(user_id)
        await self._attachment_store.clear(user_id)


__all__ = ["ConversationFileService"]

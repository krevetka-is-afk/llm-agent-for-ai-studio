"""Local filesystem storage for conversation-scoped user attachments."""

import asyncio
import shutil
from pathlib import Path
from uuid import uuid4

from ai_studio_agent_builder.application.file_policy import (
    MAX_UPLOAD_BYTES,
    sanitize_filename,
)
from ai_studio_agent_builder.application.interaction import (
    Attachment,
    UploadValidationError,
)


class LocalAttachmentStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def directory_for(self, user_id: str) -> Path:
        return self._root_dir / user_id

    def save(
        self,
        user_id: str,
        original_filename: str,
        content: bytes,
        caption: str | None = None,
    ) -> Attachment:
        if len(content) > MAX_UPLOAD_BYTES:
            raise UploadValidationError(
                f"Upload is {len(content)} bytes; limit is {MAX_UPLOAD_BYTES} bytes"
            )
        display_name = sanitize_filename(original_filename, fallback="upload.bin")
        filename = f"{uuid4().hex}_{display_name}"
        target_dir = self.directory_for(user_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / filename).write_bytes(content)
        return Attachment(
            filename=filename,
            display_name=display_name,
            caption=caption,
        )

    async def clear(self, user_id: str) -> None:
        await asyncio.to_thread(shutil.rmtree, self.directory_for(user_id), True)


__all__ = ["LocalAttachmentStore"]

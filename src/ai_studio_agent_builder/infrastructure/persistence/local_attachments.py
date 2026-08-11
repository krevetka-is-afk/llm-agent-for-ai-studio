"""Local filesystem storage for conversation-scoped user attachments."""

import asyncio
import shutil
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

from ai_studio_agent_builder.application.file_policy import (
    MAX_UPLOAD_BYTES,
    resolve_upload_path,
    sanitize_filename,
)
from ai_studio_agent_builder.application.interaction import (
    Attachment,
    UploadValidationError,
)
from ai_studio_agent_builder.application.ports.generated_artifact_store import (
    GeneratedArtifactTooLargeError,
    StoredGeneratedArtifact,
)


GENERATED_ARTIFACTS_DIRECTORY = ".generated"


class LocalAttachmentStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def directory_for(self, user_id: str) -> Path:
        return self._root_dir / user_id

    def read_text(self, base_dir: Path, filename: str) -> str:
        return resolve_upload_path(base_dir, filename).read_text(encoding="utf-8")

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

    def save_generated_artifact(
        self,
        user_id: str,
        display_name: str,
        chunks: Iterable[bytes],
        *,
        max_bytes: int,
    ) -> StoredGeneratedArtifact:
        safe_display_name = sanitize_filename(
            display_name,
            fallback="generated-file.bin",
        )
        generated_dir = self.directory_for(user_id) / GENERATED_ARTIFACTS_DIRECTORY
        generated_dir.mkdir(parents=True, exist_ok=True)
        artifact_token = uuid4().hex
        local_name = f"{artifact_token}_{safe_display_name}"
        target = generated_dir / local_name
        partial = generated_dir / f".{artifact_token}.partial"
        size_bytes = 0
        chunk_iterator = iter(chunks)
        try:
            with partial.open("xb") as destination:
                for chunk in chunk_iterator:
                    if not isinstance(chunk, bytes | bytearray | memoryview):
                        raise TypeError("Generated artifact stream returned non-bytes")
                    size_bytes += len(chunk)
                    if size_bytes > max_bytes:
                        raise GeneratedArtifactTooLargeError(
                            "Generated artifact exceeds the streaming byte limit"
                        )
                    destination.write(chunk)
            partial.replace(target)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        finally:
            close = getattr(chunk_iterator, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        return StoredGeneratedArtifact(
            local_name=local_name,
            display_name=safe_display_name,
            size_bytes=size_bytes,
        )

    def read_generated_artifact(self, user_id: str, local_name: str) -> bytes:
        generated_dir = self.directory_for(user_id) / GENERATED_ARTIFACTS_DIRECTORY
        return resolve_upload_path(generated_dir, local_name).read_bytes()

    async def clear_generated_artifacts(self, user_id: str) -> None:
        generated_dir = self.directory_for(user_id) / GENERATED_ARTIFACTS_DIRECTORY
        await asyncio.to_thread(shutil.rmtree, generated_dir, True)


__all__ = ["LocalAttachmentStore"]

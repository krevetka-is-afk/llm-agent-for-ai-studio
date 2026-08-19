"""Local filesystem storage for conversation-scoped user attachments."""

import asyncio
import logging
import os
import shutil
import stat
import threading
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

from ai_studio_agent_builder.application.file_policy import (
    MAX_UPLOAD_BYTES,
    resolve_upload_path,
    resolve_storage_directory,
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
MAX_USER_STORAGE_BYTES = 100 * 1024 * 1024
MAX_TOTAL_STORAGE_BYTES = 512 * 1024 * 1024
MAX_USER_STORED_FILES = 100
logger = logging.getLogger(__name__)
_STORAGE_LOCK = threading.RLock()


def _restrict_permissions(path: Path, mode: int) -> None:
    if os.name == "posix":
        path.chmod(mode)


def _storage_usage(directory: Path) -> tuple[int, int]:
    if not directory.exists():
        return 0, 0
    file_count = 0
    size_bytes = 0
    for path in directory.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        file_count += 1
        size_bytes += path.stat().st_size
    return file_count, size_bytes


def _clear_directory(directory: Path) -> None:
    with _STORAGE_LOCK:
        shutil.rmtree(directory, ignore_errors=True)


class LocalAttachmentStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def directory_for(self, user_id: str) -> Path:
        return resolve_storage_directory(self._root_dir, user_id)

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
        with _STORAGE_LOCK:
            display_name = sanitize_filename(original_filename, fallback="upload.bin")
            filename = f"{uuid4().hex}_{display_name}"
            target_dir = self.directory_for(user_id)
            user_files, user_bytes = _storage_usage(target_dir)
            _, total_bytes = _storage_usage(self._root_dir)
            if user_files >= MAX_USER_STORED_FILES:
                raise UploadValidationError("User file storage count limit reached")
            if user_bytes + len(content) > MAX_USER_STORAGE_BYTES:
                raise UploadValidationError("User file storage byte limit reached")
            if total_bytes + len(content) > MAX_TOTAL_STORAGE_BYTES:
                raise UploadValidationError("Application file storage quota reached")
            target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            _restrict_permissions(target_dir, stat.S_IRWXU)
            target = target_dir / filename
            with target.open("xb") as destination:
                _restrict_permissions(target, stat.S_IRUSR | stat.S_IWUSR)
                destination.write(content)
        return Attachment(
            filename=filename,
            display_name=display_name,
            caption=caption,
        )

    async def clear(self, user_id: str) -> None:
        await asyncio.to_thread(_clear_directory, self.directory_for(user_id))

    def save_generated_artifact(
        self,
        user_id: str,
        display_name: str,
        chunks: Iterable[bytes],
        *,
        max_bytes: int,
    ) -> StoredGeneratedArtifact:
        with _STORAGE_LOCK:
            safe_display_name = sanitize_filename(
                display_name,
                fallback="generated-file.bin",
            )
            user_dir = self.directory_for(user_id)
            user_files, user_bytes = _storage_usage(user_dir)
            _, total_bytes = _storage_usage(self._root_dir)
            if user_files >= MAX_USER_STORED_FILES:
                raise GeneratedArtifactTooLargeError(
                    "User file storage count limit reached"
                )
            generated_dir = user_dir / GENERATED_ARTIFACTS_DIRECTORY
            generated_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            _restrict_permissions(generated_dir, stat.S_IRWXU)
            artifact_token = uuid4().hex
            local_name = f"{artifact_token}_{safe_display_name}"
            target = generated_dir / local_name
            partial = generated_dir / f".{artifact_token}.partial"
            size_bytes = 0
            chunk_iterator = iter(chunks)
            try:
                with partial.open("xb") as destination:
                    _restrict_permissions(partial, stat.S_IRUSR | stat.S_IWUSR)
                    for chunk in chunk_iterator:
                        if not isinstance(chunk, bytes | bytearray | memoryview):
                            raise TypeError(
                                "Generated artifact stream returned non-bytes"
                            )
                        size_bytes += len(chunk)
                        if size_bytes > max_bytes:
                            raise GeneratedArtifactTooLargeError(
                                "Generated artifact exceeds the streaming byte limit"
                            )
                        if user_bytes + size_bytes > MAX_USER_STORAGE_BYTES:
                            raise GeneratedArtifactTooLargeError(
                                "User file storage byte limit reached"
                            )
                        if total_bytes + size_bytes > MAX_TOTAL_STORAGE_BYTES:
                            raise GeneratedArtifactTooLargeError(
                                "Application file storage quota reached"
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
                    except Exception as exc:
                        logger.debug(
                            "Could not close generated artifact stream category=%s",
                            type(exc).__name__,
                        )
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
        await asyncio.to_thread(_clear_directory, generated_dir)


__all__ = [
    "LocalAttachmentStore",
    "MAX_TOTAL_STORAGE_BYTES",
    "MAX_USER_STORAGE_BYTES",
    "MAX_USER_STORED_FILES",
]

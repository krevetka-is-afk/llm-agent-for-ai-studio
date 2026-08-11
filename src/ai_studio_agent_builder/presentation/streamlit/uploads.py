"""Validate Streamlit upload metadata and build attachment records."""

from collections.abc import Sequence
from typing import Protocol

from ai_studio_agent_builder.application.file_policy import MAX_UPLOAD_BYTES
from ai_studio_agent_builder.application.interaction import (
    Attachment,
    MAX_ATTACHMENTS_PER_REQUEST,
    MAX_TOTAL_UPLOAD_BYTES,
    UploadValidationError,
)


class UploadMetadata(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def size(self) -> int: ...


class UploadRecordMetadata(UploadMetadata, Protocol):
    @property
    def type(self) -> str | None: ...


def validate_uploaded_files(uploaded_files: Sequence[UploadMetadata]) -> None:
    if len(uploaded_files) > MAX_ATTACHMENTS_PER_REQUEST:
        raise UploadValidationError(
            f"За один запрос можно прикрепить не более {MAX_ATTACHMENTS_PER_REQUEST} файлов."
        )
    oversized = next(
        (file for file in uploaded_files if file.size > MAX_UPLOAD_BYTES), None
    )
    if oversized is not None:
        limit_mib = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise UploadValidationError(
            f"Файл «{oversized.name}» превышает лимит {limit_mib} МБ."
        )
    if sum(file.size for file in uploaded_files) > MAX_TOTAL_UPLOAD_BYTES:
        limit_mib = MAX_TOTAL_UPLOAD_BYTES // (1024 * 1024)
        raise UploadValidationError(
            f"Общий размер файлов превышает лимит {limit_mib} МБ."
        )


def attachment_record(
    attachment: Attachment, uploaded_file: UploadRecordMetadata
) -> dict[str, str | int]:
    return {
        "filename": attachment.filename,
        "original_filename": uploaded_file.name,
        "mime_type": uploaded_file.type or "application/octet-stream",
        "size": uploaded_file.size,
    }

"""Application ownership of conversation and preview file lifecycles."""

import logging
import mimetypes
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ai_studio_agent_builder.application.file_policy import (
    UnsafeUploadPathError,
    UploadTooLargeError,
    enforce_upload_size,
    resolve_upload_path,
)
from ai_studio_agent_builder.application.interaction import (
    AgentTestInputError,
    AgentTestRequest,
    Attachment,
    GeneratedFile,
    GeneratedFileWarning,
    MAX_ATTACHMENTS_PER_REQUEST,
    MAX_GENERATED_FILE_BYTES,
    MAX_GENERATED_FILES_PER_REQUEST,
    MAX_TOTAL_UPLOAD_BYTES,
    MAX_TOTAL_GENERATED_BYTES,
)
from ai_studio_agent_builder.application.ports.conversation_storage import (
    AttachmentStore,
    ConversationSessionStore,
)
from ai_studio_agent_builder.application.ports.file_resource_gateway import (
    FileResourceGatewayFactory,
)
from ai_studio_agent_builder.application.ports.generated_artifact_store import (
    GeneratedArtifactStore,
    GeneratedArtifactTooLargeError,
)
from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentRunPreview,
    RemoteArtifactReference,
)
from ai_studio_agent_builder.domain.runtime import (
    ExecutableAgentConfig,
    MissingCodeInterpreterToolError,
    bind_code_interpreter_files,
)


logger = logging.getLogger(__name__)
ARTIFACT_DOWNLOAD_CHUNK_BYTES = 64 * 1024
INLINE_GENERATED_MIME_TYPES = frozenset(
    {
        "application/json",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
        "text/csv",
        "text/plain",
    }
)


class ConversationFileService:
    def __init__(
        self,
        attachment_store: AttachmentStore,
        session_store: ConversationSessionStore,
        generated_artifact_store: GeneratedArtifactStore,
    ) -> None:
        self._attachment_store = attachment_store
        self._session_store = session_store
        self._generated_artifact_store = generated_artifact_store

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
        await self._generated_artifact_store.clear_generated_artifacts(user_id)
        await self._attachment_store.clear(user_id)

    def read_generated_file(self, user_id: str, local_name: str) -> bytes:
        return self._generated_artifact_store.read_generated_artifact(
            user_id,
            local_name,
        )


class PreviewInputFileLifecycle:
    """Bind local inputs to one provider request and always delete remote copies."""

    def __init__(
        self,
        attachment_store: AttachmentStore,
        gateway_factory: FileResourceGatewayFactory,
    ) -> None:
        self._attachment_store = attachment_store
        self._gateway_factory = gateway_factory

    @contextmanager
    def bind_inputs(
        self,
        request: AgentTestRequest,
        config: ExecutableAgentConfig,
    ) -> Iterator[ExecutableAgentConfig]:
        if not request.attachments:
            yield config
            return

        try:
            bind_code_interpreter_files(config, ())
        except MissingCodeInterpreterToolError as exc:
            raise AgentTestInputError(
                "Agent test attachments require Code Interpreter"
            ) from exc

        base_dir = self._attachment_store.directory_for(request.user_id)
        self._validate_local_inputs(base_dir, request.attachments)
        gateway = self._gateway_factory.create(request.credentials)
        remote_file_ids: list[str] = []
        try:
            for attachment in request.attachments:
                remote_file_ids.append(
                    gateway.upload_user_file(base_dir, attachment.filename)
                )
            yield bind_code_interpreter_files(config, remote_file_ids)
        finally:
            cleanup_failures = 0
            for file_id in remote_file_ids:
                try:
                    gateway.delete_file(file_id)
                except Exception:
                    cleanup_failures += 1
            if cleanup_failures:
                logger.warning(
                    "Preview input cleanup incomplete failed_count=%d total_count=%d",
                    cleanup_failures,
                    len(remote_file_ids),
                )

    @staticmethod
    def _validate_local_inputs(
        base_dir: Path,
        attachments: tuple[Attachment, ...],
    ) -> None:
        if len(attachments) > MAX_ATTACHMENTS_PER_REQUEST:
            raise AgentTestInputError(
                f"Agent test accepts at most {MAX_ATTACHMENTS_PER_REQUEST} attachments"
            )
        filenames = [attachment.filename for attachment in attachments]
        if any(
            attachment.file_id is not None
            or not isinstance(attachment.filename, str)
            or not attachment.filename.strip()
            for attachment in attachments
        ):
            raise AgentTestInputError(
                "Agent test attachments must reference trusted local files"
            )
        if len(set(filenames)) != len(filenames):
            raise AgentTestInputError("Agent test attachment names must be unique")

        total_bytes = 0
        try:
            for filename in filenames:
                path = resolve_upload_path(base_dir, filename)
                enforce_upload_size(path, source_name=filename)
                total_bytes += path.stat().st_size
        except (UnsafeUploadPathError, UploadTooLargeError) as exc:
            raise AgentTestInputError(
                "Agent test attachment violates the upload policy"
            ) from exc
        if total_bytes > MAX_TOTAL_UPLOAD_BYTES:
            raise AgentTestInputError(
                "Agent test attachments exceed the total upload limit"
            )


class PreviewOutputFileLifecycle:
    """Materialize bounded output artifacts and clean all known remote resources."""

    def __init__(
        self,
        generated_artifact_store: GeneratedArtifactStore,
        gateway_factory: FileResourceGatewayFactory,
    ) -> None:
        self._generated_artifact_store = generated_artifact_store
        self._gateway_factory = gateway_factory

    def materialize_outputs(
        self,
        request: AgentTestRequest,
        preview: AgentRunPreview,
    ) -> tuple[tuple[GeneratedFile, ...], tuple[GeneratedFileWarning, ...]]:
        references = _deduplicate_artifacts(preview.generated_artifacts)
        container_ids = _deduplicate_strings(
            (*preview.container_ids, *(ref.container_id for ref in references))
        )
        if not references and not container_ids:
            return (), ()

        warning_codes: set[str] = set()
        try:
            gateway = self._gateway_factory.create(request.credentials)
        except Exception as exc:
            logger.warning(
                "Generated artifact gateway unavailable category=%s",
                type(exc).__name__,
            )
            if references:
                warning_codes.add("download_failed")
            warning_codes.add("cleanup_failed")
            return (), _artifact_warnings(warning_codes)

        generated_files: list[GeneratedFile] = []
        saved_bytes = 0
        try:
            candidates = references[:MAX_GENERATED_FILES_PER_REQUEST]
            if len(references) > len(candidates):
                warning_codes.add("too_many")
            for reference in candidates:
                remaining_bytes = MAX_TOTAL_GENERATED_BYTES - saved_bytes
                if remaining_bytes <= 0:
                    warning_codes.add("too_large")
                    continue
                try:
                    stored = self._generated_artifact_store.save_generated_artifact(
                        request.user_id,
                        reference.filename,
                        gateway.iter_file_bytes(
                            reference.file_id,
                            chunk_size=ARTIFACT_DOWNLOAD_CHUNK_BYTES,
                        ),
                        max_bytes=min(MAX_GENERATED_FILE_BYTES, remaining_bytes),
                    )
                except GeneratedArtifactTooLargeError:
                    warning_codes.add("too_large")
                    continue
                except Exception as exc:
                    logger.warning(
                        "Generated artifact download failed category=%s",
                        type(exc).__name__,
                    )
                    warning_codes.add("download_failed")
                    continue

                mime_type = (
                    mimetypes.guess_type(stored.display_name, strict=False)[0]
                    or "application/octet-stream"
                )
                generated_files.append(
                    GeneratedFile(
                        local_name=stored.local_name,
                        display_name=stored.display_name,
                        mime_type=mime_type,
                        size_bytes=stored.size_bytes,
                        inline_preview_allowed=mime_type in INLINE_GENERATED_MIME_TYPES,
                    )
                )
                saved_bytes += stored.size_bytes
        finally:
            cleanup_failures = 0
            for reference in references:
                try:
                    gateway.delete_file(reference.file_id)
                except Exception:
                    cleanup_failures += 1
            for container_id in container_ids:
                try:
                    gateway.delete_container(container_id)
                except Exception:
                    cleanup_failures += 1
            if cleanup_failures:
                logger.warning(
                    "Generated artifact cleanup incomplete failed_count=%d",
                    cleanup_failures,
                )
                warning_codes.add("cleanup_failed")

        return tuple(generated_files), _artifact_warnings(warning_codes)


def _deduplicate_artifacts(
    references: tuple[RemoteArtifactReference, ...],
) -> tuple[RemoteArtifactReference, ...]:
    unique: list[RemoteArtifactReference] = []
    seen_file_ids: set[str] = set()
    for reference in references:
        if reference.file_id in seen_file_ids:
            continue
        seen_file_ids.add(reference.file_id)
        unique.append(reference)
    return tuple(unique)


def _deduplicate_strings(values: tuple[str | None, ...]) -> tuple[str, ...]:
    unique: list[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in unique:
            unique.append(value)
    return tuple(unique)


def _artifact_warnings(codes: set[str]) -> tuple[GeneratedFileWarning, ...]:
    order = ("too_many", "too_large", "download_failed", "cleanup_failed")
    return tuple(GeneratedFileWarning(code=code) for code in order if code in codes)


__all__ = [
    "ConversationFileService",
    "PreviewInputFileLifecycle",
    "PreviewOutputFileLifecycle",
]

"""Application ownership of conversation and preview file lifecycles."""

import logging
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
    MAX_ATTACHMENTS_PER_REQUEST,
    MAX_TOTAL_UPLOAD_BYTES,
)
from ai_studio_agent_builder.application.ports.conversation_storage import (
    AttachmentStore,
    ConversationSessionStore,
)
from ai_studio_agent_builder.application.ports.file_resource_gateway import (
    FileResourceGatewayFactory,
)
from ai_studio_agent_builder.domain.runtime import (
    ExecutableAgentConfig,
    MissingCodeInterpreterToolError,
    bind_code_interpreter_files,
)


logger = logging.getLogger(__name__)


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


__all__ = ["ConversationFileService", "PreviewInputFileLifecycle"]

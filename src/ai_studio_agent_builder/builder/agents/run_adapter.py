"""Agents SDK implementation of the application-owned builder run port."""

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from agents import OpenAIProvider, RunConfig
from openai import OpenAIError

from ai_studio_agent_builder.application.dto import AIStudioCredentials
from ai_studio_agent_builder.application.errors import AIStudioRequestError
from ai_studio_agent_builder.application.interaction import (
    Attachment,
    MAX_ATTACHMENTS_PER_REQUEST,
    MAX_TOTAL_UPLOAD_BYTES,
    UploadValidationError,
)
from ai_studio_agent_builder.application.file_policy import resolve_upload_path
from ai_studio_agent_builder.application.ports.builder_run import (
    BuilderRunOutcome,
    BuilderRunRequest,
)
from ai_studio_agent_builder.builder.context import RequestContext
from ai_studio_agent_builder.builder.result_assembly import (
    AgentRunResult,
    ResultAssembler,
    merge_agent_runs,
    render_result_text,
    result_part_to_record,
)
from ai_studio_agent_builder.domain.content_policy import (
    ensure_model_output_allowed,
)
from ai_studio_agent_builder.domain.routing import ConversationOptions

from .sdk_event_adapter import AgentRunCollector


ClientFactory = Callable[[AIStudioCredentials], Any]
FileUploader = Callable[[Any, Path, str], str]
logger = logging.getLogger(__name__)


class UnsupportedConversationStateError(RuntimeError):
    """Raised when no builder agent is registered for the selected state."""


class BuilderAgentsRunAdapter:
    """Run builder agents without exposing the Agents SDK to application code."""

    def __init__(
        self,
        *,
        coordinator_agent: Any,
        rag_agent: Any,
        one_prompt_agent: Any,
        sync_client_factory: ClientFactory,
        async_client_factory: ClientFactory,
        file_uploader: FileUploader,
    ) -> None:
        self._agents = {
            ConversationOptions.COORDINATOR: coordinator_agent,
            ConversationOptions.RAG: rag_agent,
            ConversationOptions.ONE_PROMPT: one_prompt_agent,
        }
        self._sync_client_factory = sync_client_factory
        self._async_client_factory = async_client_factory
        self._file_uploader = file_uploader
        self._result_assembler = ResultAssembler()

    async def run(self, request: BuilderRunRequest) -> BuilderRunOutcome:
        try:
            return await self._run(request)
        except OpenAIError as exc:
            raise AIStudioRequestError("AI Studio request failed") from exc

    async def _run(self, request: BuilderRunRequest) -> BuilderRunOutcome:
        state = request.conversation_state
        context = RequestContext(
            user_id=request.user_id,
            request_id=request.request_id,
            user_files_dir=request.user_files_dir,
            client=self._sync_client_factory(request.credentials),
            state=state,
            folder_id=request.credentials.folder_id,
        )
        run_config = RunConfig(
            model_provider=OpenAIProvider(
                openai_client=self._async_client_factory(request.credentials),
                use_responses=True,
            ),
            tracing_disabled=True,
            trace_include_sensitive_data=False,
        )
        initial_vector_store_id = self._current_vector_store_id(state)
        uploaded_file_ids: list[str] = []
        try:
            return await self._run_with_context(
                request,
                context,
                run_config,
                uploaded_file_ids,
            )
        except BaseException:
            await self._cleanup_failed_run(
                context,
                uploaded_file_ids,
                initial_vector_store_id=initial_vector_store_id,
            )
            raise

    async def _run_with_context(
        self,
        request: BuilderRunRequest,
        context: RequestContext,
        run_config: RunConfig,
        uploaded_file_ids: list[str],
    ) -> BuilderRunOutcome:
        state = request.conversation_state
        selected_agent = state.state
        attachments = request.attachments
        if selected_agent is ConversationOptions.RAG:
            attachments = await self._ensure_uploaded_files(
                attachments,
                context.client,
                request.user_files_dir,
                uploaded_file_ids,
            )
            self._authorize_attachment_ids(context, attachments)

        first_run = await self._collect_run(
            self._agent_for(selected_agent),
            self._build_input(
                request,
                attachments,
                trusted_filenames_by_file_id=context.filenames_by_file_id,
            ),
            context,
            run_config,
        )
        runs = [first_run]
        responded_by = selected_agent
        if (
            selected_agent is ConversationOptions.COORDINATOR
            and state.state is not selected_agent
        ):
            responded_by = state.state
            attachments = await self._ensure_uploaded_files(
                attachments,
                context.client,
                request.user_files_dir,
                uploaded_file_ids,
            )
            self._authorize_attachment_ids(context, attachments)
            runs.append(
                await self._collect_run(
                    self._agent_for(responded_by),
                    self._build_input(
                        request,
                        attachments,
                        trusted_filenames_by_file_id=context.filenames_by_file_id,
                    ),
                    context,
                    run_config,
                )
            )

        parts = self._result_assembler.assemble(
            merge_agent_runs(*runs),
            responded_by,
            context.filenames_by_file_id,
            specification=state.latest_agent_specification,
        )
        part_records = tuple(result_part_to_record(part) for part in parts)
        ensure_model_output_allowed(part_records)
        return BuilderRunOutcome(
            text=render_result_text(parts),
            parts=part_records,
            selected_agent=selected_agent,
            responded_by=responded_by,
            next_state=state.state,
        )

    def _agent_for(self, state: ConversationOptions) -> Any:
        try:
            return self._agents[state]
        except KeyError as exc:
            raise UnsupportedConversationStateError(
                f"Unsupported conversation state: {state}"
            ) from exc

    async def _ensure_uploaded_files(
        self,
        attachments: tuple[Attachment, ...],
        client: Any,
        base_dir: Path,
        uploaded_file_ids: list[str],
    ) -> tuple[Attachment, ...]:
        self._validate_attachment_registry(attachments)
        total_upload_bytes = sum(
            resolve_upload_path(base_dir, attachment.filename).stat().st_size
            for attachment in attachments
            if attachment.file_id is None
        )
        if total_upload_bytes > MAX_TOTAL_UPLOAD_BYTES:
            raise UploadValidationError(
                "Attachments exceed the total request limit: "
                f"{total_upload_bytes} > {MAX_TOTAL_UPLOAD_BYTES} bytes"
            )
        uploaded_attachments: list[Attachment] = []
        for attachment in attachments:
            if attachment.file_id is not None:
                uploaded_attachments.append(attachment)
                continue
            file_id = await asyncio.to_thread(
                self._file_uploader,
                client,
                base_dir,
                attachment.filename,
            )
            uploaded_file_ids.append(file_id)
            uploaded_attachments.append(replace(attachment, file_id=file_id))
        return tuple(uploaded_attachments)

    async def _cleanup_failed_run(
        self,
        context: RequestContext,
        uploaded_file_ids: list[str],
        *,
        initial_vector_store_id: str | None,
    ) -> None:
        current_vector_store_id = self._current_vector_store_id(context.state)
        if (
            current_vector_store_id is not None
            and current_vector_store_id != initial_vector_store_id
        ):
            try:
                await asyncio.to_thread(
                    context.client.vector_stores.delete,
                    current_vector_store_id,
                )
            except Exception as exc:
                logger.warning(
                    "Failed builder run left vector store cleanup incomplete",
                    extra={
                        "user_id": context.user_id,
                        "request_id": context.request_id,
                        "error_type": type(exc).__name__,
                    },
                )
        for file_id in reversed(uploaded_file_ids):
            try:
                await asyncio.to_thread(context.client.files.delete, file_id)
            except Exception as exc:
                logger.warning(
                    "Failed builder run left input file cleanup incomplete",
                    extra={
                        "user_id": context.user_id,
                        "request_id": context.request_id,
                        "error_type": type(exc).__name__,
                    },
                )

    @staticmethod
    def _current_vector_store_id(state: Any) -> str | None:
        specification = state.agent_specification
        if specification is None:
            return None
        value = specification.parameters.get("index_id")
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _validate_attachment_registry(attachments: tuple[Attachment, ...]) -> None:
        if len(attachments) > MAX_ATTACHMENTS_PER_REQUEST:
            raise UploadValidationError(
                "Too many attachments in one request: "
                f"{len(attachments)} > {MAX_ATTACHMENTS_PER_REQUEST}"
            )
        seen: set[str] = set()
        for attachment in attachments:
            filename = attachment.filename
            if filename in seen:
                raise UploadValidationError(
                    f"Duplicate attachment filename: {filename}"
                )
            seen.add(filename)
            requested = Path(filename)
            if requested.is_absolute() or ".." in requested.parts:
                raise UploadValidationError(
                    "Attachment filename must be a current-request relative path"
                )
            if ".previews" in requested.parts:
                raise UploadValidationError("Preview artifacts cannot be uploaded")

    @staticmethod
    def _authorize_attachment_ids(
        context: RequestContext,
        attachments: tuple[Attachment, ...],
    ) -> None:
        current_filenames_by_file_id = {
            attachment.file_id: attachment.display_name or attachment.filename
            for attachment in attachments
            if attachment.file_id is not None
        }
        context.state.register_pending_files(current_filenames_by_file_id)
        context.allowed_file_ids = frozenset(context.state.pending_file_ids)
        context.filenames_by_file_id = context.state.pending_filenames_by_file_id

    @staticmethod
    def _build_input(
        request: BuilderRunRequest,
        attachments: tuple[Attachment, ...],
        *,
        trusted_filenames_by_file_id: Mapping[str, str] | None = None,
    ) -> str:
        caption = next(
            (attachment.caption for attachment in attachments if attachment.caption),
            None,
        )
        if trusted_filenames_by_file_id:
            filenames = ", ".join(trusted_filenames_by_file_id.values())
            return (
                "Files are securely available for this RAG workflow: "
                f"{filenames}. Create the requested vector index using the "
                "server-managed files; do not ask the user to upload them again "
                "and do not request file IDs. "
                f"User request: {caption or request.text or ''}\n"
            )
        if attachments:
            filenames = ", ".join(
                attachment.display_name or attachment.filename
                for attachment in attachments
            )
            noun = "file" if len(attachments) == 1 else "files"
            if caption:
                return f"Uploaded {noun} by user: {filenames} with request: {caption}\n"
            return f"Uploaded {noun} by user: {filenames}\n"
        return f"User request: {request.text or ''}\n"

    @staticmethod
    async def _collect_run(
        agent: Any,
        message: str,
        context: RequestContext,
        run_config: RunConfig,
    ) -> AgentRunResult:
        collector = AgentRunCollector()
        async for event in agent.respond(
            message=message,
            context=context,
            run_config=run_config,
        ):
            collector.consume(event)
        return collector.build()


__all__ = ["BuilderAgentsRunAdapter", "UnsupportedConversationStateError"]

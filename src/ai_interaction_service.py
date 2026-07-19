import asyncio
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents import OpenAIProvider, RunConfig
from config import AIServiceConfig
from context import (
    AIStudioCredentials,
    ConversationOptions,
    ConversationState,
    RequestContext,
    get_api_key_client,
    get_async_api_key_client,
)
from custom_agents.coordinator_agent import build_coordinator_agent
from custom_agents.one_prompt_agent import build_one_prompt_agent
from custom_agents.rag_agent import build_rag_agent
from custom_agents.tools.upload_files import upload_local_file
from result_assembly import (
    AgentRunResult,
    AgentRunCollector,
    ResultAssembler,
    ResultPart,
    merge_agent_runs,
    render_result_text,
)
from session import get_session


@dataclass(frozen=True)
class Attachment:
    filename: str
    display_name: str | None = None
    caption: str | None = None
    file_id: str | None = None


@dataclass(frozen=True)
class InteractionRequest:
    user_id: str
    text: str | None
    credentials: AIStudioCredentials
    conversation_state: ConversationState
    user_files_dir: Path
    attachment: Attachment | None = None
    attachments: tuple[Attachment, ...] = ()


@dataclass(frozen=True)
class InteractionResult:
    text: str
    parts: tuple[ResultPart, ...]
    selected_agent: ConversationOptions
    responded_by: ConversationOptions
    next_state: ConversationOptions


class UnsupportedConversationStateError(RuntimeError):
    pass


class AIInteractionService:
    def __init__(
        self,
        config: AIServiceConfig,
        *,
        rag_agent: Any | None = None,
        one_prompt_agent: Any | None = None,
        coordinator_agent: Any | None = None,
    ):
        self._config = config
        self._rag_agent = rag_agent or build_rag_agent(config.rag_model)
        self._one_prompt_agent = one_prompt_agent or build_one_prompt_agent(
            config.one_prompt
        )
        self._coordinator_agent = coordinator_agent or build_coordinator_agent(
            config.consultant
        )
        self._result_assembler = ResultAssembler()

    def user_files_dir(self, user_id: str) -> Path:
        return self._config.paths.uploaded_files_dir / user_id

    def save_attachment(
        self,
        user_id: str,
        original_filename: str,
        content: bytes,
        caption: str | None = None,
    ) -> Attachment:
        safe_filename = Path(original_filename.replace("\\", "/")).name
        if safe_filename in {"", ".", ".."}:
            safe_filename = "upload.bin"
        filename = f"{uuid4().hex}_{safe_filename}"
        target_dir = self.user_files_dir(user_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / filename).write_bytes(content)
        return Attachment(
            filename=filename,
            display_name=safe_filename,
            caption=caption,
        )

    async def validate_connection(self, credentials: AIStudioCredentials) -> None:
        client = get_api_key_client(credentials, self._config.connection)
        await asyncio.to_thread(
            client.responses.create,
            model=(
                f"gpt://{credentials.folder_id}/"
                f"{self._config.one_prompt.model_name}"
            ),
            input="Ответьте ровно: OK",
            max_output_tokens=2,
        )

    async def interact(self, request: InteractionRequest) -> InteractionResult:
        selected_agent = request.conversation_state.state
        agent = self._agent_for(selected_agent)
        context = RequestContext(
            user_id=request.user_id,
            user_files_dir=request.user_files_dir,
            client=get_api_key_client(request.credentials, self._config.connection),
            state=request.conversation_state,
            api_key=request.credentials.api_key,
            folder_id=request.credentials.folder_id,
        )
        run_config = RunConfig(
            model_provider=OpenAIProvider(
                openai_client=get_async_api_key_client(
                    request.credentials, self._config.connection
                ),
                use_responses=True,
            )
        )
        attachments = self._attachments(request)
        if selected_agent is ConversationOptions.RAG:
            attachments = await self._ensure_uploaded_files(
                attachments, context.client, request.user_files_dir
            )
        first_run = await self._collect_run(
            agent,
            self._build_input(request, attachments),
            context,
            run_config,
        )
        runs = [first_run]
        responded_by = selected_agent
        if (
            selected_agent is ConversationOptions.COORDINATOR
            and request.conversation_state.state is not selected_agent
        ):
            responded_by = request.conversation_state.state
            attachments = await self._ensure_uploaded_files(
                attachments, context.client, request.user_files_dir
            )
            runs.append(
                await self._collect_run(
                    self._agent_for(responded_by),
                    self._build_input(request, attachments),
                    context,
                    run_config,
                )
            )
        combined_run = merge_agent_runs(*runs)
        parts = self._result_assembler.assemble(
            combined_run,
            responded_by,
            {
                attachment.file_id: attachment.display_name or attachment.filename
                for attachment in attachments
                if attachment.file_id is not None
            },
        )
        return InteractionResult(
            text=render_result_text(parts),
            parts=parts,
            selected_agent=selected_agent,
            responded_by=responded_by,
            next_state=request.conversation_state.state,
        )

    async def reset_conversation(self, user_id: str) -> None:
        db_paths = {
            self._config.rag_model.sessions_db_path,
            self._config.one_prompt.sessions_db_path,
            self._config.consultant.sessions_db_path,
        }
        for db_path in db_paths:
            await get_session(user_id, db_path).clear_session()

    def _agent_for(self, state: ConversationOptions):
        if state is ConversationOptions.COORDINATOR:
            return self._coordinator_agent
        if state is ConversationOptions.RAG:
            return self._rag_agent
        if state is ConversationOptions.ONE_PROMPT:
            return self._one_prompt_agent
        raise UnsupportedConversationStateError(f"Unsupported conversation state: {state}")

    @staticmethod
    def _attachments(request: InteractionRequest) -> tuple[Attachment, ...]:
        attachments = request.attachments
        if request.attachment is not None:
            attachments = (*attachments, request.attachment)
        return attachments

    @staticmethod
    async def _ensure_uploaded_files(
        attachments: tuple[Attachment, ...], client: Any, base_dir: Path
    ) -> tuple[Attachment, ...]:
        uploaded_attachments: list[Attachment] = []
        for attachment in attachments:
            if attachment.file_id is not None:
                uploaded_attachments.append(attachment)
                continue
            file_id = await asyncio.to_thread(
                upload_local_file, client, base_dir, attachment.filename
            )
            uploaded_attachments.append(replace(attachment, file_id=file_id))
        return tuple(uploaded_attachments)

    @staticmethod
    def _build_input(
        request: InteractionRequest, attachments: tuple[Attachment, ...] | None = None
    ) -> str:
        if attachments is None:
            attachments = AIInteractionService._attachments(request)
        if attachments:
            filenames = ", ".join(
                attachment.display_name or attachment.filename
                for attachment in attachments
            )
            caption = next(
                (
                    attachment.caption
                    for attachment in attachments
                    if attachment.caption
                ),
                None,
            )
            noun = "file" if len(attachments) == 1 else "files"
            file_ids = [attachment.file_id for attachment in attachments]
            if all(file_ids):
                available_files = "; ".join(
                    f"{attachment.display_name or attachment.filename} "
                    f"(file_id: {attachment.file_id})"
                    for attachment in attachments
                )
                return (
                    f"Files are already uploaded to AI Studio: {available_files}. "
                    "Create the requested vector index using these file_ids now. "
                    "Do not ask the user to upload the files again. "
                    f"User request: {caption or request.text or ''}\n"
                )
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

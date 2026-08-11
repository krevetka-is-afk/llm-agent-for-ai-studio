import asyncio
import hashlib
import logging
import shutil
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents import OpenAIProvider, RunConfig
from ai_studio_agent_builder.application.dto import AIStudioCredentials
from ai_studio_agent_builder.application.file_policy import (
    MAX_UPLOAD_BYTES,
    resolve_upload_path,
    sanitize_filename,
)
from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentCitation,
    AgentProviderError,
    AgentRunPreview,
    AgentRunner,
    AgentRunnerError,
)
from ai_studio_agent_builder.application.builder_state import ConversationState
from ai_studio_agent_builder.builder.agents.sdk_event_adapter import AgentRunCollector
from ai_studio_agent_builder.builder.context import RequestContext
from ai_studio_agent_builder.builder.result_assembly import (
    AgentRunResult,
    AgentSpecificationResultPart,
    MarkdownResultPart,
    ResultAssembler,
    ResultPart,
    merge_agent_runs,
    render_result_text,
)
from ai_studio_agent_builder.config import AIServiceConfig
from ai_studio_agent_builder.domain.routing import (
    ConversationOptions,
    resolve_explicit_route,
)
from ai_studio_agent_builder.domain.specification import (
    AgentSpecification,
    InvalidSpecificationRecordError,
)
from ai_studio_agent_builder.domain.specification_codec import (
    InvalidSpecificationJSONError,
    InvalidSpecificationRootError,
    load_agent_specification,
    loads_agent_specification,
)
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.client_factory import (
    get_api_key_client,
    get_async_api_key_client,
)
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.files_gateway import (
    upload_local_file,
)
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.responses_runner import (
    YandexResponsesAgentRunner,
)
from ai_studio_agent_builder.infrastructure.persistence.agent_sessions import (
    get_session,
)
from ai_studio_agent_builder.infrastructure.observability.logging import bind_logger
from agent_runtime import (
    AgentRuntimeCompilationError,
    ExecutableAgentConfig,
    compile_agent_specification,
)
from custom_agents.coordinator_agent import build_coordinator_agent
from custom_agents.one_prompt_agent import build_one_prompt_agent
from custom_agents.rag_agent import build_rag_agent


logger = logging.getLogger(__name__)


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
    request_id: str = field(default_factory=lambda: uuid4().hex)
    attachment: Attachment | None = None
    attachments: tuple[Attachment, ...] = ()


@dataclass(frozen=True)
class InteractionResult:
    text: str
    parts: tuple[ResultPart, ...]
    selected_agent: ConversationOptions
    responded_by: ConversationOptions
    next_state: ConversationOptions


@dataclass(frozen=True)
class AgentTestRequest:
    user_id: str
    credentials: AIStudioCredentials
    specification_record: Mapping[str, Any]
    user_input: str
    request_id: str = field(default_factory=lambda: uuid4().hex)


@dataclass(frozen=True)
class AgentTestResult:
    response_id: str
    output_text: str
    citations: tuple[AgentCitation, ...]
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class UnsupportedConversationStateError(RuntimeError):
    pass


class UploadValidationError(ValueError):
    pass


class AgentTestInputError(ValueError):
    pass


class AgentSpecificationImportError(ValueError):
    """Raised when an uploaded AgentSpecification cannot be imported."""


AgentRunnerFactory = Callable[[Any, str], AgentRunner]

MAX_ATTACHMENTS_PER_REQUEST = 5
MAX_TOTAL_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_AGENT_TEST_INPUT_LENGTH = 10_000
UPLOAD_RETENTION_POLICY = (
    "User upload directories are request-scoped for model access and are removed "
    "when the user resets the conversation."
)


class AIInteractionService:
    def __init__(
        self,
        config: AIServiceConfig,
        *,
        rag_agent: Any | None = None,
        one_prompt_agent: Any | None = None,
        coordinator_agent: Any | None = None,
        agent_runner_factory: AgentRunnerFactory | None = None,
    ):
        self._config = config
        self._rag_agent = rag_agent or build_rag_agent(config.rag_model)
        self._one_prompt_agent = one_prompt_agent or build_one_prompt_agent(
            config.one_prompt
        )
        self._coordinator_agent = coordinator_agent or build_coordinator_agent(
            config.consultant
        )
        self._agent_runner_factory = (
            agent_runner_factory or self._build_yandex_agent_runner
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
        if len(content) > MAX_UPLOAD_BYTES:
            raise UploadValidationError(
                f"Upload is {len(content)} bytes; limit is {MAX_UPLOAD_BYTES} bytes"
            )
        safe_filename = self._sanitize_display_filename(original_filename)
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
                f"gpt://{credentials.folder_id}/{self._config.one_prompt.model_name}"
            ),
            input="Ответьте ровно: OK",
            max_output_tokens=2,
        )

    async def test_agent_specification(
        self,
        request: AgentTestRequest,
    ) -> AgentTestResult:
        user_input = request.user_input.strip()
        if not user_input:
            raise AgentTestInputError("Agent test input must not be empty")
        if len(user_input) > MAX_AGENT_TEST_INPUT_LENGTH:
            raise AgentTestInputError(
                f"Agent test input exceeds {MAX_AGENT_TEST_INPUT_LENGTH} characters"
            )

        request_logger = bind_logger(
            logger,
            user_id=_pseudonymous_user_id(request.user_id),
            request_id=request.request_id,
        )
        started_at = time.monotonic()
        try:
            specification = load_agent_specification(request.specification_record)
            executable_config = self.prepare_agent_runtime(
                request.specification_record,
                specification=specification,
            )
            native_tool_types = tuple(
                tool["type"]
                for tool in executable_config.tools
                if isinstance(tool.get("type"), str)
            )
            request_logger.info(
                "Generated agent test started template=%s tools=%s",
                specification.template.value,
                native_tool_types,
            )
            client = get_api_key_client(
                request.credentials,
                self._config.connection,
            )
            runner = self._agent_runner_factory(
                client,
                request.credentials.folder_id,
            )
            preview = await asyncio.to_thread(
                runner.run,
                executable_config,
                user_input,
            )
        except (
            InvalidSpecificationRecordError,
            AgentRuntimeCompilationError,
            AgentRunnerError,
        ) as exc:
            request_logger.warning(
                "Generated agent test failed category=%s duration_ms=%d",
                type(exc).__name__,
                _duration_ms(started_at),
            )
            raise
        except Exception as exc:
            request_logger.error(
                "Generated agent test failed category=unexpected duration_ms=%d",
                _duration_ms(started_at),
            )
            raise AgentProviderError() from exc
        request_logger.info(
            "Generated agent test completed response_id=%s duration_ms=%d",
            preview.response_id,
            _duration_ms(started_at),
        )
        return _agent_test_result(preview)

    def prepare_agent_runtime(
        self,
        specification_record: Mapping[str, Any],
        *,
        specification: AgentSpecification | None = None,
    ) -> ExecutableAgentConfig:
        trusted_specification = specification or load_agent_specification(
            specification_record
        )
        return compile_agent_specification(
            trusted_specification,
            runtime=self._config.generated_agent_runtime,
        )

    async def interact(self, request: InteractionRequest) -> InteractionResult:
        request_logger = bind_logger(
            logger,
            user_id=request.user_id,
            request_id=request.request_id,
        )
        request_logger.info("AI interaction started")
        try:
            result = await self._interact(request)
        except Exception as exc:
            request_logger.exception(
                "AI interaction failed",
                extra={"error_type": type(exc).__name__},
            )
            raise
        request_logger.info(
            "AI interaction completed selected_agent=%s responded_by=%s next_state=%s",
            result.selected_agent.name,
            result.responded_by.name,
            result.next_state.name,
        )
        return result

    async def _interact(self, request: InteractionRequest) -> InteractionResult:
        working_state = request.conversation_state.copy()
        imported_specification = self._imported_specification(request, working_state)
        if imported_specification is not None:
            return self._import_result(
                request,
                working_state,
                imported_specification,
            )
        routing_decision = resolve_explicit_route(request.text)
        if routing_decision is not None:
            previous_state = working_state.state
            working_state.update_state(routing_decision.target)
            if previous_state is not routing_decision.target:
                bind_logger(
                    logger,
                    user_id=request.user_id,
                    request_id=request.request_id,
                ).info(
                    "Explicit routing override previous=%s target=%s reason=%s",
                    previous_state.name,
                    routing_decision.target.name,
                    routing_decision.reason.value,
                )
        selected_agent = working_state.state
        agent = self._agent_for(selected_agent)
        context = RequestContext(
            user_id=request.user_id,
            request_id=request.request_id,
            user_files_dir=request.user_files_dir,
            client=get_api_key_client(request.credentials, self._config.connection),
            state=working_state,
            folder_id=request.credentials.folder_id,
        )
        run_config = RunConfig(
            model_provider=OpenAIProvider(
                openai_client=get_async_api_key_client(
                    request.credentials, self._config.connection
                ),
                use_responses=True,
            ),
            tracing_disabled=True,
            trace_include_sensitive_data=False,
        )
        attachments = self._attachments(request)
        if selected_agent is ConversationOptions.RAG:
            attachments = await self._ensure_uploaded_files(
                attachments, context.client, request.user_files_dir
            )
            self._authorize_attachment_ids(context, attachments)
        first_run = await self._collect_run(
            agent,
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
            and working_state.state is not selected_agent
        ):
            responded_by = working_state.state
            attachments = await self._ensure_uploaded_files(
                attachments, context.client, request.user_files_dir
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
        combined_run = merge_agent_runs(*runs)
        parts = self._result_assembler.assemble(
            combined_run,
            responded_by,
            context.filenames_by_file_id,
            specification=working_state.latest_agent_specification,
        )
        result = InteractionResult(
            text=render_result_text(parts),
            parts=parts,
            selected_agent=selected_agent,
            responded_by=responded_by,
            next_state=working_state.state,
        )
        request.conversation_state.commit_from(working_state)
        return result

    def _imported_specification(
        self,
        request: InteractionRequest,
        state: ConversationState,
    ) -> AgentSpecification | None:
        attachments = self._attachments(request)
        json_attachments = tuple(
            attachment
            for attachment in attachments
            if self._is_json_attachment(attachment)
        )
        if not json_attachments or not self._requests_specification_import(
            request.text, json_attachments
        ):
            return None
        if len(json_attachments) > 1:
            raise AgentSpecificationImportError(
                "Прикрепите только один файл AgentSpecification JSON за запрос."
            )

        attachment = json_attachments[0]
        path = resolve_upload_path(request.user_files_dir, attachment.filename)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise AgentSpecificationImportError(
                "Файл спецификации должен быть валидным UTF-8 JSON."
            ) from exc
        except OSError as exc:
            raise AgentSpecificationImportError(
                "Не удалось прочитать прикреплённый файл спецификации."
            ) from exc

        try:
            specification = loads_agent_specification(content)
        except InvalidSpecificationJSONError as exc:
            location = (
                f": строка {exc.lineno}, столбец {exc.colno}"
                if exc.lineno is not None and exc.colno is not None
                else ""
            )
            raise AgentSpecificationImportError(
                f"Файл спецификации содержит некорректный JSON{location}."
            ) from exc
        except InvalidSpecificationRootError as exc:
            raise AgentSpecificationImportError(
                "Корень файла спецификации должен быть JSON-объектом."
            ) from exc
        except InvalidSpecificationRecordError as exc:
            raise AgentSpecificationImportError(
                f"Файл не соответствует схеме AgentSpecification 1.0: {exc}"
            ) from exc

        state.import_agent_specification(specification)
        return specification

    @staticmethod
    def _is_json_attachment(attachment: Attachment) -> bool:
        filename = attachment.display_name or attachment.filename
        return filename.lower().endswith(".json")

    @staticmethod
    def _requests_specification_import(
        text: str | None,
        attachments: tuple[Attachment, ...],
    ) -> bool:
        normalized = (text or "").lower()
        if "спецификац" in normalized or "agent-specification" in normalized:
            return True
        return any(
            "agent-specification"
            in (attachment.display_name or attachment.filename).lower()
            for attachment in attachments
        )

    @staticmethod
    def _import_result(
        request: InteractionRequest,
        state: ConversationState,
        specification: AgentSpecification,
    ) -> InteractionResult:
        index_note = ""
        if specification.template.value == "rag":
            index_id = specification.parameters.get("index_id")
            index_name = specification.parameters.get("index_name")
            if isinstance(index_id, str) and isinstance(index_name, str):
                index_note = (
                    f"\nИндекс: {index_name} (id: {index_id})"
                    "\nPDF повторно загружать не требуется: он нужен только "
                    "для пересоздания индекса."
                    "\nДоступность индекса будет проверена при тестовом запуске."
                )
        text = (
            "Спецификация агента распознана и прошла локальную проверку."
            f"\nШаблон: {specification.template.value}"
            f"\nСтатус: {specification.status.value}"
            f"{index_note}"
            "\nОткройте блок спецификации и запустите тестовый запрос."
        )
        parts: tuple[ResultPart, ...] = (
            AgentSpecificationResultPart(specification=specification),
            MarkdownResultPart(text=text),
        )
        request.conversation_state.commit_from(state)
        return InteractionResult(
            text=render_result_text(parts),
            parts=parts,
            selected_agent=state.state,
            responded_by=state.state,
            next_state=state.state,
        )

    async def reset_conversation(self, user_id: str) -> None:
        db_paths = {
            self._config.rag_model.sessions_db_path,
            self._config.one_prompt.sessions_db_path,
            self._config.consultant.sessions_db_path,
        }
        for db_path in db_paths:
            await get_session(user_id, db_path).clear_session()
        await asyncio.to_thread(shutil.rmtree, self.user_files_dir(user_id), True)

    def _agent_for(self, state: ConversationOptions):
        if state is ConversationOptions.COORDINATOR:
            return self._coordinator_agent
        if state is ConversationOptions.RAG:
            return self._rag_agent
        if state is ConversationOptions.ONE_PROMPT:
            return self._one_prompt_agent
        raise UnsupportedConversationStateError(
            f"Unsupported conversation state: {state}"
        )

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
        AIInteractionService._validate_attachment_registry(attachments)
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
                upload_local_file, client, base_dir, attachment.filename
            )
            uploaded_attachments.append(replace(attachment, file_id=file_id))
        return tuple(uploaded_attachments)

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
        context: RequestContext, attachments: tuple[Attachment, ...]
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
        request: InteractionRequest,
        attachments: tuple[Attachment, ...] | None = None,
        *,
        trusted_filenames_by_file_id: Mapping[str, str] | None = None,
    ) -> str:
        if attachments is None:
            attachments = AIInteractionService._attachments(request)
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
    def _sanitize_display_filename(original_filename: str) -> str:
        return sanitize_filename(original_filename, fallback="upload.bin")

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

    @staticmethod
    def _build_yandex_agent_runner(client: Any, folder_id: str) -> AgentRunner:
        return YandexResponsesAgentRunner(client, folder_id=folder_id)


def _agent_test_result(preview: AgentRunPreview) -> AgentTestResult:
    return AgentTestResult(
        response_id=preview.response_id,
        output_text=preview.output_text,
        citations=preview.citations,
        input_tokens=preview.input_tokens,
        output_tokens=preview.output_tokens,
        total_tokens=preview.total_tokens,
    )


def _pseudonymous_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]


def _duration_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))

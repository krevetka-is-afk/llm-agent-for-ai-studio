import asyncio
import hashlib
import logging
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ai_studio_agent_builder.application import interaction as interaction_contract
from ai_studio_agent_builder.application.dto import AIStudioCredentials
from ai_studio_agent_builder.application.interaction import (
    AgentSpecificationImportError,
    AgentTestInputError,
    AgentTestRequest,
    AgentTestResult,
    Attachment,
    InteractionRequest,
    InteractionResult,
    MAX_AGENT_TEST_INPUT_LENGTH,
)
from ai_studio_agent_builder.application.file_policy import resolve_upload_path
from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentProviderError,
    AgentRunPreview,
    AgentRunner,
    AgentRunnerError,
    AgentRunnerFactory,
)
from ai_studio_agent_builder.application.builder_state import ConversationState
from ai_studio_agent_builder.application.ports.builder_run import (
    BuilderRunPort,
    BuilderRunRequest,
)
from ai_studio_agent_builder.application.ports.connection import ConnectionValidator
from ai_studio_agent_builder.application.ports.conversation_storage import (
    AttachmentStore,
    ConversationSessionStore,
)
from ai_studio_agent_builder.builder.agents.run_adapter import BuilderAgentsRunAdapter
from ai_studio_agent_builder.builder.agents.coordinator_agent import (
    build_coordinator_agent,
)
from ai_studio_agent_builder.builder.agents.one_prompt_agent import (
    build_one_prompt_agent,
)
from ai_studio_agent_builder.builder.agents.rag_agent import build_rag_agent
from ai_studio_agent_builder.builder.result_assembly import (
    AgentSpecificationResultPart,
    MarkdownResultPart,
    ResultPart,
    render_result_text,
    result_part_to_record,
)
from ai_studio_agent_builder.application.settings import AIServiceConfig
from ai_studio_agent_builder.domain.routing import resolve_explicit_route
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
    YandexAgentRunnerFactory,
)
from ai_studio_agent_builder.infrastructure.persistence.agent_sessions import (
    SQLiteConversationSessionStore,
    get_session,
)
from ai_studio_agent_builder.infrastructure.persistence.local_attachments import (
    LocalAttachmentStore,
)
from ai_studio_agent_builder.infrastructure.observability.logging import bind_logger
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.connection import (
    YandexConnectionValidator,
)
from agent_runtime import (
    AgentRuntimeCompilationError,
    ExecutableAgentConfig,
    compile_agent_specification,
)


logger = logging.getLogger(__name__)
UPLOAD_RETENTION_POLICY = interaction_contract.UPLOAD_RETENTION_POLICY
MAX_ATTACHMENTS_PER_REQUEST = interaction_contract.MAX_ATTACHMENTS_PER_REQUEST
MAX_TOTAL_UPLOAD_BYTES = interaction_contract.MAX_TOTAL_UPLOAD_BYTES
UploadValidationError = interaction_contract.UploadValidationError


LegacyAgentRunnerFactory = Callable[[Any, str], AgentRunner]


class AIInteractionService:
    def __init__(
        self,
        config: AIServiceConfig,
        *,
        rag_agent: Any | None = None,
        one_prompt_agent: Any | None = None,
        coordinator_agent: Any | None = None,
        agent_runner_factory: LegacyAgentRunnerFactory | None = None,
        builder_run_port: BuilderRunPort | None = None,
        connection_validator: ConnectionValidator | None = None,
        generated_agent_runner_factory: AgentRunnerFactory | None = None,
        attachment_store: AttachmentStore | None = None,
        conversation_session_store: ConversationSessionStore | None = None,
    ):
        self._config = config
        if builder_run_port is None:
            builder_run_port = BuilderAgentsRunAdapter(
                rag_agent=rag_agent or build_rag_agent(config.rag_model, get_session),
                one_prompt_agent=one_prompt_agent
                or build_one_prompt_agent(config.one_prompt, get_session),
                coordinator_agent=coordinator_agent
                or build_coordinator_agent(config.consultant, get_session),
                sync_client_factory=lambda credentials: get_api_key_client(
                    credentials,
                    config.connection,
                ),
                async_client_factory=lambda credentials: get_async_api_key_client(
                    credentials,
                    config.connection,
                ),
                file_uploader=lambda client, base_dir, filename: upload_local_file(
                    client,
                    base_dir,
                    filename,
                ),
            )
        self._builder_run_port = builder_run_port
        self._connection_validator = connection_validator or YandexConnectionValidator(
            lambda credentials: get_api_key_client(credentials, config.connection),
            model_name=config.one_prompt.model_name,
        )
        self._agent_runner_factory = (
            generated_agent_runner_factory
            or YandexAgentRunnerFactory(
                lambda credentials: get_api_key_client(
                    credentials,
                    config.connection,
                ),
                runner_builder=agent_runner_factory,
            )
        )
        self._attachment_store = attachment_store or LocalAttachmentStore(
            config.paths.uploaded_files_dir
        )
        self._conversation_session_store = (
            conversation_session_store
            or SQLiteConversationSessionStore(
                {
                    config.rag_model.sessions_db_path,
                    config.one_prompt.sessions_db_path,
                    config.consultant.sessions_db_path,
                }
            )
        )

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

    async def validate_connection(self, credentials: AIStudioCredentials) -> None:
        await self._connection_validator.validate(credentials)

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
            runner = self._agent_runner_factory.create(request.credentials)
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
        outcome = await self._builder_run_port.run(
            BuilderRunRequest(
                user_id=request.user_id,
                request_id=request.request_id,
                text=request.text,
                credentials=request.credentials,
                conversation_state=working_state,
                user_files_dir=request.user_files_dir,
                attachments=self._attachments(request),
            )
        )
        result = InteractionResult(
            text=outcome.text,
            parts=outcome.parts,
            selected_agent=outcome.selected_agent,
            responded_by=outcome.responded_by,
            next_state=outcome.next_state,
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
            parts=tuple(result_part_to_record(part) for part in parts),
            selected_agent=state.state,
            responded_by=state.state,
            next_state=state.state,
        )

    async def reset_conversation(self, user_id: str) -> None:
        await self._conversation_session_store.clear(user_id)
        await self._attachment_store.clear(user_id)

    @staticmethod
    def _attachments(request: InteractionRequest) -> tuple[Attachment, ...]:
        attachments = request.attachments
        if request.attachment is not None:
            attachments = (*attachments, request.attachment)
        return attachments


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

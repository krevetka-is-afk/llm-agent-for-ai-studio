"""Application orchestration for one Agent Builder conversation turn."""

import logging

from ai_studio_agent_builder.application.builder_state import ConversationState
from ai_studio_agent_builder.application.errors import AIStudioRequestError
from ai_studio_agent_builder.application.interaction import (
    AgentSpecificationImportError,
    Attachment,
    InteractionRequest,
    InteractionResult,
)
from ai_studio_agent_builder.application.ports.builder_run import (
    BuilderRunPort,
    BuilderRunRequest,
)
from ai_studio_agent_builder.application.ports.conversation_storage import (
    AttachmentReader,
)
from ai_studio_agent_builder.domain.content_policy import (
    ContentPolicyViolationError,
    POLICY_REFUSAL_MESSAGE,
    assess_user_content,
    ensure_model_output_allowed,
)
from ai_studio_agent_builder.domain.routing import resolve_explicit_route
from ai_studio_agent_builder.domain.specification import (
    AgentSpecification,
    InvalidSpecificationRecordError,
)
from ai_studio_agent_builder.domain.specification_codec import (
    InvalidSpecificationJSONError,
    InvalidSpecificationRootError,
    dump_agent_specification,
    loads_agent_specification,
)


logger = logging.getLogger(__name__)


class BuilderConversationService:
    def __init__(
        self,
        builder_run_port: BuilderRunPort,
        attachment_reader: AttachmentReader,
    ) -> None:
        self._builder_run_port = builder_run_port
        self._attachment_reader = attachment_reader

    async def interact(self, request: InteractionRequest) -> InteractionResult:
        request_logger = _bind_request_logger(request.user_id, request.request_id)
        request_logger.info("AI interaction started")
        try:
            result = await self._interact(request)
        except AIStudioRequestError:
            request_logger.warning("AI interaction rejected by provider")
            raise
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
        input_decision = assess_user_content(
            request.text,
            tuple(
                value
                for attachment in self._attachments(request)
                for value in (
                    attachment.caption,
                    attachment.display_name,
                    attachment.filename,
                )
                if value is not None
            ),
        )
        if input_decision.violation is not None:
            self._log_policy_rejection(request, input_decision.violation.value)
            return self._policy_refusal_result(request.conversation_state)

        working_state = request.conversation_state.copy()
        try:
            imported_specification = self._imported_specification(
                request,
                working_state,
            )
        except ContentPolicyViolationError as exc:
            self._log_policy_rejection(request, exc.kind.value)
            return self._policy_refusal_result(request.conversation_state)
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
                _bind_request_logger(request.user_id, request.request_id).info(
                    "Explicit routing override previous=%s target=%s reason=%s",
                    previous_state.name,
                    routing_decision.target.name,
                    routing_decision.reason.value,
                )

        try:
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
            ensure_model_output_allowed(outcome.text, outcome.parts)
        except ContentPolicyViolationError as exc:
            self._log_policy_rejection(request, exc.kind.value)
            return self._policy_refusal_result(request.conversation_state)
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
            request.text,
            json_attachments,
        ):
            return None
        if len(json_attachments) > 1:
            raise AgentSpecificationImportError(
                "Прикрепите только один файл AgentSpecification JSON за запрос."
            )

        attachment = json_attachments[0]
        try:
            content = self._attachment_reader.read_text(
                request.user_files_dir,
                attachment.filename,
            )
        except UnicodeDecodeError as exc:
            raise AgentSpecificationImportError(
                "Файл спецификации должен быть валидным UTF-8 JSON."
            ) from exc
        except OSError as exc:
            raise AgentSpecificationImportError(
                "Не удалось прочитать прикреплённый файл спецификации."
            ) from exc

        decision = assess_user_content(content)
        if decision.violation is not None:
            raise ContentPolicyViolationError(decision.violation)

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
        request.conversation_state.commit_from(state)
        return InteractionResult(
            text=f"{_render_specification_summary(specification)}\n\n{text}",
            parts=(
                {
                    "kind": "agent_specification",
                    "specification": dump_agent_specification(specification),
                },
                {"kind": "markdown", "text": text},
            ),
            selected_agent=state.state,
            responded_by=state.state,
            next_state=state.state,
        )

    @staticmethod
    def _attachments(request: InteractionRequest) -> tuple[Attachment, ...]:
        attachments = request.attachments
        if request.attachment is not None:
            attachments = (*attachments, request.attachment)
        return attachments

    @staticmethod
    def _policy_refusal_result(state: ConversationState) -> InteractionResult:
        return InteractionResult(
            text=POLICY_REFUSAL_MESSAGE,
            parts=({"kind": "markdown", "text": POLICY_REFUSAL_MESSAGE},),
            selected_agent=state.state,
            responded_by=state.state,
            next_state=state.state,
        )

    @staticmethod
    def _log_policy_rejection(
        request: InteractionRequest,
        reason: str,
    ) -> None:
        _bind_request_logger(request.user_id, request.request_id).warning(
            "AI interaction blocked by content policy reason=%s",
            reason,
        )


def _render_specification_summary(specification: AgentSpecification) -> str:
    lines = [
        "Спецификация агента",
        f"Шаблон: {specification.template.value}",
        f"Статус: {specification.status.value}",
    ]
    if specification.missing_fields:
        lines.append("Недостающие поля: " + ", ".join(specification.missing_fields))
    return "\n".join(lines)


def _bind_request_logger(user_id: str, request_id: str) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(
        logger,
        {"user_id": user_id, "request_id": request_id},
    )


__all__ = ["BuilderConversationService"]

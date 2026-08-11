import asyncio
import logging
from collections.abc import Coroutine, Mapping, Sequence
from typing import Any, Protocol, TypeVar
from uuid import uuid4

import streamlit as st
from openai import OpenAIError
from streamlit.runtime.uploaded_file_manager import UploadedFile

from ai_interaction_service import (
    AIInteractionService,
    AgentSpecificationImportError,
    AgentTestRequest,
    AgentTestResult,
    Attachment,
    InteractionRequest,
    InteractionResult,
    UploadValidationError,
)
from ai_studio_agent_builder.application.file_policy import MAX_UPLOAD_BYTES
from context import ConversationState
from custom_agents.tools.vector_index import VectorIndexPollingError
from logging_config import bind_logger
from result_assembly import result_part_to_record
from ui.api_key_store import ApiKeyConnection
from ui.agent_test_panel import AgentSpecificationActions, AgentTestCallback
from ui.attachments import render_attachment
from ui.connection import credentials_from_connection
from ui.result_view import render_result_parts
from ui.uploads import attachment_record, validate_uploaded_files


logger = logging.getLogger(__name__)
T = TypeVar("T")


class NamedUpload(Protocol):
    name: str


def render_chat(
    ai_service: AIInteractionService,
    connection: ApiKeyConnection | None,
    connection_id: str,
) -> None:
    _initialize_chat_state()
    agent_actions = build_agent_specification_actions(
        ai_service,
        connection,
        connection_id,
    )
    _render_history(ai_service, connection_id, agent_actions)

    submission = st.chat_input(
        "Введите сообщение или приложите файлы",
        accept_file="multiple",
        max_upload_size=MAX_UPLOAD_BYTES // (1024 * 1024),
        disabled=connection is None,
    )
    if submission is None or connection is None:
        return

    prompt, uploaded_files = _submission_parts(submission)
    if not prompt and not uploaded_files:
        return

    request_id = uuid4().hex
    attachments = _save_attachments(
        ai_service,
        connection_id,
        prompt,
        uploaded_files,
        request_id,
    )
    if attachments is None:
        return

    _append_and_render_user_message(
        ai_service,
        connection_id,
        prompt,
        uploaded_files,
        attachments,
    )
    _append_and_render_assistant_message(
        ai_service,
        connection,
        connection_id,
        prompt,
        attachments,
        request_id,
        agent_actions,
    )


def build_user_content(prompt: str, uploaded_files: Sequence[NamedUpload]) -> str:
    if not uploaded_files:
        return prompt
    if len(uploaded_files) == 1:
        return prompt or f"Прикреплён файл: {uploaded_files[0].name}"
    filenames = ", ".join(uploaded_file.name for uploaded_file in uploaded_files)
    return prompt or f"Прикреплены файлы: {filenames}"


def interaction_error_message(exc: Exception) -> str:
    if isinstance(exc, OpenAIError):
        return "AI Studio отклонил запрос. Проверьте ключ, каталог и права."
    if isinstance(exc, AgentSpecificationImportError):
        return str(exc)
    if isinstance(exc, UploadValidationError):
        return str(exc)
    if isinstance(exc, VectorIndexPollingError):
        return "AI Studio не завершил создание индекса. Повторите попытку позднее."
    return "Не удалось выполнить запрос к AI Studio. Повторите попытку."


async def answer(
    ai_service: AIInteractionService,
    connection: ApiKeyConnection,
    user_id: str,
    conversation_state: ConversationState,
    prompt: str,
    attachments: tuple[Attachment, ...],
    request_id: str,
) -> InteractionResult:
    return await ai_service.interact(
        InteractionRequest(
            user_id=user_id,
            request_id=request_id,
            text=prompt,
            credentials=credentials_from_connection(connection),
            conversation_state=conversation_state,
            user_files_dir=ai_service.user_files_dir(user_id),
            attachments=attachments,
        )
    )


def _initialize_chat_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversation_state" not in st.session_state:
        st.session_state.conversation_state = ConversationState()


def _render_history(
    ai_service: AIInteractionService,
    connection_id: str,
    agent_actions: AgentSpecificationActions,
) -> None:
    for message_index, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            result_parts = message.get("result_parts")
            if isinstance(result_parts, list):
                message_id = message.get("id")
                key_prefix = (
                    message_id
                    if isinstance(message_id, str)
                    else f"legacy-message-{message_index}"
                )
                render_result_parts(
                    result_parts,
                    key_prefix=key_prefix,
                    agent_actions=agent_actions,
                )
            else:
                st.markdown(message["content"])
            attachments = message.get("attachments")
            if isinstance(attachments, list):
                for attachment in attachments:
                    if isinstance(attachment, Mapping):
                        render_attachment(ai_service, connection_id, attachment)
            else:
                attachment = message.get("attachment")
                if isinstance(attachment, Mapping):
                    render_attachment(ai_service, connection_id, attachment)


def _submission_parts(
    submission: str | Any,
) -> tuple[str, list[UploadedFile]]:
    if isinstance(submission, str):
        return submission, []
    return submission.text, submission.files


def _save_attachments(
    ai_service: AIInteractionService,
    connection_id: str,
    prompt: str,
    uploaded_files: list[UploadedFile],
    request_id: str,
) -> tuple[Attachment, ...] | None:
    try:
        validate_uploaded_files(uploaded_files)
        return tuple(
            ai_service.save_attachment(
                connection_id,
                uploaded_file.name,
                uploaded_file.getvalue(),
                caption=prompt or None,
            )
            for uploaded_file in uploaded_files
        )
    except UploadValidationError as exc:
        st.error(str(exc))
    except OSError as exc:
        bind_logger(logger, user_id=connection_id, request_id=request_id).exception(
            "Could not persist uploaded files",
            extra={"error_type": type(exc).__name__},
        )
        st.error("Не удалось сохранить загруженный файл. Повторите попытку.")
    return None


def _append_and_render_user_message(
    ai_service: AIInteractionService,
    connection_id: str,
    prompt: str,
    uploaded_files: list[UploadedFile],
    attachments: tuple[Attachment, ...],
) -> None:
    user_content = build_user_content(prompt, uploaded_files)
    message: dict[str, Any] = {"role": "user", "content": user_content}
    if attachments:
        message["attachments"] = [
            attachment_record(attachment, uploaded_file)
            for attachment, uploaded_file in zip(
                attachments, uploaded_files, strict=True
            )
        ]
    st.session_state.messages.append(message)
    with st.chat_message("user"):
        st.markdown(user_content)
        for attachment in message.get("attachments", []):
            render_attachment(ai_service, connection_id, attachment)


def _append_and_render_assistant_message(
    ai_service: AIInteractionService,
    connection: ApiKeyConnection,
    connection_id: str,
    prompt: str,
    attachments: tuple[Attachment, ...],
    request_id: str,
    agent_actions: AgentSpecificationActions,
) -> None:
    assistant_message_id = f"{request_id}-assistant"
    with st.chat_message("assistant"):
        with st.spinner("Генерируется ответ..."):
            result, answer_text = _request_answer(
                ai_service,
                connection,
                connection_id,
                prompt,
                attachments,
                request_id,
            )
            result_parts = (
                [result_part_to_record(part) for part in result.parts]
                if result is not None
                else []
            )
            if result_parts:
                render_result_parts(
                    result_parts,
                    key_prefix=assistant_message_id,
                    agent_actions=agent_actions,
                )
            else:
                st.markdown(answer_text)

    assistant_message: dict[str, Any] = {
        "id": assistant_message_id,
        "role": "assistant",
        "content": answer_text,
    }
    if result_parts:
        assistant_message["result_parts"] = result_parts
    st.session_state.messages.append(assistant_message)


def _request_answer(
    ai_service: AIInteractionService,
    connection: ApiKeyConnection,
    connection_id: str,
    prompt: str,
    attachments: tuple[Attachment, ...],
    request_id: str,
) -> tuple[InteractionResult | None, str]:
    try:
        result = _run_async(
            answer(
                ai_service,
                connection,
                connection_id,
                st.session_state.conversation_state,
                prompt,
                attachments,
                request_id,
            )
        )
        return result, result.text
    except Exception as exc:
        request_logger = bind_logger(
            logger,
            user_id=connection_id,
            request_id=request_id,
        )
        if isinstance(
            exc, (AgentSpecificationImportError, OpenAIError, UploadValidationError)
        ):
            request_logger.warning(
                "AI interaction rejected error_type=%s", type(exc).__name__
            )
        else:
            request_logger.exception(
                "AI interaction failed",
                extra={"error_type": type(exc).__name__},
            )
        return None, interaction_error_message(exc)


def _run_async(awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def build_agent_specification_actions(
    ai_service: AIInteractionService,
    connection: ApiKeyConnection | None,
    connection_id: str,
) -> AgentSpecificationActions:
    test_callback: AgentTestCallback | None = None
    if connection is not None:

        def run_agent_test(
            specification: Mapping[str, Any],
            user_input: str,
            request_id: str,
        ) -> AgentTestResult:
            return _run_async(
                ai_service.test_agent_specification(
                    AgentTestRequest(
                        user_id=connection_id,
                        credentials=credentials_from_connection(connection),
                        specification_record=specification,
                        user_input=user_input,
                        request_id=request_id,
                    )
                )
            )

        test_callback = run_agent_test

    return AgentSpecificationActions(
        runtime_config_json=lambda specification: ai_service.prepare_agent_runtime(
            specification
        ).to_json(),
        test_agent=test_callback,
    )

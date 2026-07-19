import asyncio
import logging
import mimetypes
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast, Coroutine, Mapping, Optional, Protocol, TypeVar
from uuid import uuid4

import streamlit as st
from openai import OpenAIError
from streamlit.runtime.uploaded_file_manager import UploadedFile

from ai_interaction_service import (
    AIInteractionService,
    Attachment,
    InteractionRequest,
    InteractionResult,
    MAX_ATTACHMENTS_PER_REQUEST,
    MAX_TOTAL_UPLOAD_BYTES,
    UploadValidationError,
)
from custom_agents.tools.upload_files import MAX_UPLOAD_BYTES
from custom_agents.tools.vector_index import VectorIndexPollingError
from ui.api_key_store import ApiKeyConnection, ApiKeyStoreError, EncryptedApiKeyStore
from config import WebUIConfig, load_web_ui_config
from context import AIStudioCredentials, ConversationState
from result_assembly import result_part_to_record


logger = logging.getLogger(__name__)

st.set_page_config(page_title="AI Studio Chat", page_icon="AI", layout="centered")

AI_STUDIO_URL = "https://aistudio.yandex.ru/"
FOLDERS_CONSOLE_URL = "https://console.yandex.cloud/folders"
API_KEY_GUIDE_URL = (
    "https://aistudio.yandex.ru/docs/ru/ai-studio/operations/get-api-key.html"
)
FOLDER_ID_GUIDE_URL = (
    "https://yandex.cloud/ru/docs/resource-manager/operations/folder/get-id"
)
MAX_TEXT_PREVIEW_BYTES = 100_000


@st.cache_resource
def _load_services() -> tuple[WebUIConfig, EncryptedApiKeyStore, AIInteractionService]:
    config = load_web_ui_config()
    return (
        config,
        EncryptedApiKeyStore(
            config.api_key_store.storage_path, config.api_key_store.encryption_key
        ),
        AIInteractionService(config.ai_service),
    )


def _connection_id() -> str:
    if "connection_id" not in st.session_state:
        st.session_state.connection_id = f"web-{uuid4().hex}"
    return st.session_state.connection_id


def _reset_chat(ai_service: AIInteractionService, user_id: str) -> None:
    st.session_state.messages = []
    st.session_state.conversation_state = ConversationState()
    _run_async(ai_service.reset_conversation(user_id))


def _credentials(connection: ApiKeyConnection) -> AIStudioCredentials:
    return AIStudioCredentials(
        api_key=connection.api_key,
        folder_id=connection.folder_id,
    )


def _render_connection(
    config: WebUIConfig,
    store: EncryptedApiKeyStore,
    ai_service: AIInteractionService,
    connection_id: str,
) -> Optional[ApiKeyConnection]:
    st.sidebar.header("Yandex Cloud")
    try:
        connection = store.get(connection_id)
    except ApiKeyStoreError:
        st.sidebar.error("Не удалось прочитать сохранённое подключение.")
        return None

    if connection is None:
        st.sidebar.caption(
            "Нужны API-ключ и ID каталога, в котором будут списываться расходы."
        )
        ai_studio_column, folders_column = st.sidebar.columns(2)
        with ai_studio_column:
            st.link_button("AI Studio (1)", AI_STUDIO_URL)
        with st.sidebar.expander("Инструкция", expanded=False):
            st.caption("Ключ показывается только один раз.")

            st.markdown(
                "1. Переходите на сайт AI Studio (1) и нажмите на `Начать работу` или `Войти`.\n"
                "2. Выберите нужный каталог и скопируйте его ID, для этого наведите курсор на интерфейс выбора каталога и появится скрытая кнопка `ID`, при нажатии копирование произойдет автоматически.\n"
                "3. Возвращайтесь на страницу диалогового интерфейса и вставьте в поле `ID каталога`.\n"
                "4. Переходите на сайт AI Studio (1) и нажмите `Создать API-ключ`. Сразу скопируйте секретную часть ключа.\n"
                "5. Возвращайтесь на страницу диалогового интерфейса и вставьте в поле `API-ключ` в диалоговом интерфейсе.\n"
                "6. Когда оба поля заполнены, нажмите `Проверить и подключить`."
            )

            st.markdown(
                "Дополнительно можете воспользоваться официальной документацией:\n"
                f"[Инструкция по ключу]({API_KEY_GUIDE_URL}) · "
                f"[Где найти ID каталога]({FOLDER_ID_GUIDE_URL})"
            )
        with st.sidebar.form("api-key-connection", clear_on_submit=True):
            folder_id = st.text_input("ID каталога")
            api_key = st.text_input("API-ключ", type="password")
            submitted = st.form_submit_button("Проверить и подключить", type="primary")
        if not submitted:
            return None
        api_key = api_key.strip()
        folder_id = folder_id.strip()
        if not api_key or not folder_id:
            st.sidebar.error("Укажите API-ключ и ID каталога.")
            return None
        try:
            with st.spinner("Проверяем доступ к AI Studio..."):
                _run_async(
                    ai_service.validate_connection(
                        AIStudioCredentials(api_key=api_key, folder_id=folder_id)
                    )
                )
            store.save(connection_id, api_key, folder_id)
        except OpenAIError:
            st.sidebar.error(
                "AI Studio отклонил подключение. Проверьте ключ, каталог и роли сервисного аккаунта."
            )
            return None
        except ApiKeyStoreError:
            st.sidebar.error("Не удалось сохранить подключение.")
            return None
        _reset_chat(ai_service, connection_id)
        st.rerun()

    st.sidebar.success("Подключение настроено")
    st.sidebar.code(connection.folder_id, language=None)
    if st.sidebar.button("Отключить ключ"):
        store.delete(connection_id)
        _reset_chat(ai_service, connection_id)
        st.rerun()
    return connection


async def _answer(
    ai_service: AIInteractionService,
    connection: ApiKeyConnection,
    user_id: str,
    conversation_state: ConversationState,
    prompt: str,
    attachments: tuple[Attachment, ...],
) -> InteractionResult:
    return await ai_service.interact(
        InteractionRequest(
            user_id=user_id,
            text=prompt,
            credentials=_credentials(connection),
            conversation_state=conversation_state,
            user_files_dir=ai_service.user_files_dir(user_id),
            attachments=attachments,
        )
    )


def _attachment_record(
    attachment: Attachment, uploaded_file: UploadedFile
) -> dict[str, str | int]:
    return {
        "filename": attachment.filename,
        "original_filename": uploaded_file.name,
        "mime_type": uploaded_file.type or "application/octet-stream",
        "size": uploaded_file.size,
    }


class UploadMetadata(Protocol):
    name: str
    size: int


def _validate_uploaded_files(uploaded_files: Sequence[UploadMetadata]) -> None:
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


def _render_attachment(
    ai_service: AIInteractionService,
    user_id: str,
    attachment: Mapping[str, Any],
) -> None:
    filename = attachment.get("filename")
    if not isinstance(filename, str) or Path(filename).name != filename:
        st.warning("Файл недоступен.")
        return

    original_filename = str(attachment.get("original_filename") or filename)
    mime_type = str(
        attachment.get("mime_type")
        or mimetypes.guess_type(original_filename)[0]
        or "application/octet-stream"
    )
    path = ai_service.user_files_dir(user_id) / filename
    try:
        data = path.read_bytes()
    except OSError:
        st.warning(f"Файл «{original_filename}» больше недоступен.")
        return

    size = attachment.get("size")
    size_label = f" · {int(size):,} байт" if isinstance(size, int) else ""
    st.caption(f"📎 {original_filename}{size_label}")
    st.download_button(
        "Скачать файл",
        data=data,
        file_name=original_filename,
        mime=mime_type,
        key=f"download-{filename}",
    )
    with st.expander("Просмотреть файл"):
        _render_attachment_preview(data, mime_type)


def _render_attachment_preview(data: bytes, mime_type: str) -> None:
    if mime_type.startswith("image/"):
        st.image(data)
        return
    if mime_type == "application/pdf":
        st.info(
            "Предпросмотр PDF отключён для безопасности. "
            "Скачайте файл, чтобы открыть его."
        )
        return
    if mime_type.startswith("audio/"):
        st.audio(data, format=mime_type)
        return
    if mime_type.startswith("video/"):
        st.video(data, format=mime_type)
        return
    if mime_type.startswith("text/") or mime_type in {
        "application/json",
        "application/xml",
    }:
        preview = data[:MAX_TEXT_PREVIEW_BYTES].decode("utf-8", errors="replace")
        st.code(preview)
        if len(data) > MAX_TEXT_PREVIEW_BYTES:
            st.caption("Показаны первые 100 000 байт. Полную версию можно скачать.")
        return
    st.info(
        "Предпросмотр для этого формата недоступен. Скачайте файл, чтобы открыть его."
    )


def _render_result_parts(parts: Sequence[Any]) -> None:
    for raw_part in parts:
        if not isinstance(raw_part, Mapping):
            continue
        part = cast(Mapping[str, Any], raw_part)
        kind = part.get("kind")
        if kind == "vector_index":
            _render_vector_index_result(part)
        elif kind == "markdown":
            text = part.get("text")
            if isinstance(text, str) and text:
                st.markdown(text)


def _render_vector_index_result(part: Mapping[str, Any]) -> None:
    index_name = part.get("index_name")
    index_id = part.get("index_id")
    if not isinstance(index_name, str) or not isinstance(index_id, str):
        return
    with st.container(border=True):
        st.markdown("#### 🤖 Созданный векторный индекс")
        name_column, id_column = st.columns(2)
        with name_column:
            st.markdown("**Имя индекса**")
            st.code(index_name, language=None)
        with id_column:
            st.markdown("**ID индекса**")
            st.code(index_id, language=None)

        files = part.get("files")
        if isinstance(files, list) and files:
            st.markdown("**Файлы в индексе**")
            for number, raw_file in enumerate(files, start=1):
                if not isinstance(raw_file, Mapping):
                    continue
                file = cast(Mapping[str, Any], raw_file)
                filename = file.get("filename")
                file_id = file.get("file_id")
                if isinstance(filename, str) and isinstance(file_id, str):
                    st.text(f"{number}. {filename} (file_id: {file_id})")

        expires_after_days = part.get("expires_after_days")
        if isinstance(expires_after_days, int):
            st.caption(
                "Индекс автоматически удаляется через "
                f"{expires_after_days} день после последней активности."
            )


T = TypeVar("T")


def _run_async(awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def main() -> None:
    st.title("AI Studio Chat")
    st.caption("Запросы выполняются в каталоге, связанном с вашим API-ключом.")
    st.caption(
        "Для RAG приложите несколько файлов и напишите: «Создай индекс из файлов»."
    )

    config, store, ai_service = _load_services()
    connection_id = _connection_id()
    connection = _render_connection(config, store, ai_service, connection_id)

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversation_state" not in st.session_state:
        st.session_state.conversation_state = ConversationState()
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            result_parts = message.get("result_parts")
            if isinstance(result_parts, list):
                _render_result_parts(result_parts)
            else:
                st.markdown(message["content"])
            attachments = message.get("attachments")
            if isinstance(attachments, list):
                for attachment in attachments:
                    if isinstance(attachment, Mapping):
                        _render_attachment(ai_service, connection_id, attachment)
            else:
                attachment = message.get("attachment")
                if isinstance(attachment, Mapping):
                    _render_attachment(ai_service, connection_id, attachment)

    submission = st.chat_input(
        "Введите сообщение или приложите файлы",
        accept_file="multiple",
        max_upload_size=MAX_UPLOAD_BYTES // (1024 * 1024),
        disabled=connection is None,
    )
    if submission is None or connection is None:
        return

    if isinstance(submission, str):
        prompt = submission
        uploaded_files: list[UploadedFile] = []
    else:
        prompt = submission.text
        uploaded_files = submission.files

    if not prompt and not uploaded_files:
        return

    try:
        _validate_uploaded_files(uploaded_files)
        attachments = tuple(
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
        return
    except OSError:
        st.error("Не удалось сохранить загруженный файл. Повторите попытку.")
        return

    if not uploaded_files:
        user_content = prompt
    elif len(uploaded_files) == 1:
        user_content = prompt or f"Прикреплён файл: {uploaded_files[0].name}"
    else:
        filenames = ", ".join(uploaded_file.name for uploaded_file in uploaded_files)
        user_content = prompt or f"Прикреплены файлы: {filenames}"
    message: dict[str, Any] = {"role": "user", "content": user_content}
    if attachments:
        message["attachments"] = [
            _attachment_record(attachment, uploaded_file)
            for attachment, uploaded_file in zip(
                attachments, uploaded_files, strict=True
            )
        ]
    st.session_state.messages.append(message)
    with st.chat_message("user"):
        st.markdown(user_content)
        for attachment in message.get("attachments", []):
            _render_attachment(ai_service, connection_id, attachment)

    with st.chat_message("assistant"):
        with st.spinner("Генерируется ответ..."):
            result = None
            try:
                result = _run_async(
                    _answer(
                        ai_service,
                        connection,
                        connection_id,
                        st.session_state.conversation_state,
                        prompt,
                        attachments,
                    )
                )
                answer = result.text
            except OpenAIError:
                logger.warning(
                    "AI Studio rejected interaction",
                    extra={"user_id": connection_id},
                )
                answer = "AI Studio отклонил запрос. Проверьте ключ, каталог и права."
            except UploadValidationError as exc:
                logger.warning(
                    "Upload validation rejected interaction",
                    extra={"user_id": connection_id},
                )
                answer = str(exc)
            except VectorIndexPollingError:
                logger.exception(
                    "Vector index lifecycle failed",
                    extra={"user_id": connection_id},
                )
                answer = (
                    "AI Studio не завершил создание индекса. Повторите попытку позднее."
                )
            except Exception as exc:
                logger.exception(
                    "AI interaction failed",
                    extra={
                        "user_id": connection_id,
                        "error_type": type(exc).__name__,
                    },
                )
                answer = "Не удалось выполнить запрос к AI Studio. Повторите попытку."
            result_parts = (
                [result_part_to_record(part) for part in result.parts]
                if result is not None
                else []
            )
            if result_parts:
                _render_result_parts(result_parts)
            else:
                st.markdown(answer)
    assistant_message: dict[str, Any] = {"role": "assistant", "content": answer}
    if result_parts:
        assistant_message["result_parts"] = result_parts
    st.session_state.messages.append(assistant_message)


if __name__ == "__main__":
    main()

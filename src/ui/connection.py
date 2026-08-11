import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

import streamlit as st
from openai import OpenAIError

from ai_interaction_service import AIInteractionService
from ai_studio_agent_builder.application.ports.api_key_store import (
    ApiKeyConnection,
    ApiKeyStore,
    ApiKeyStoreError,
)
from context import AIStudioCredentials, ConversationState
from ui.agent_test_panel import clear_agent_test_previews
from ui.user_guidance import AI_STUDIO_URL


API_KEY_GUIDE_URL = (
    "https://aistudio.yandex.ru/docs/ru/ai-studio/operations/get-api-key.html"
)
FOLDER_ID_GUIDE_URL = (
    "https://yandex.cloud/ru/docs/resource-manager/operations/folder/get-id"
)
T = TypeVar("T")


def credentials_from_connection(connection: ApiKeyConnection) -> AIStudioCredentials:
    return AIStudioCredentials(
        api_key=connection.api_key,
        folder_id=connection.folder_id,
    )


def render_connection(
    store: ApiKeyStore,
    ai_service: AIInteractionService,
    connection_id: str,
) -> ApiKeyConnection | None:
    st.sidebar.header("Yandex Cloud")
    try:
        connection = store.get(connection_id)
    except ApiKeyStoreError:
        st.sidebar.error("Не удалось прочитать сохранённое подключение.")
        return None

    if connection is None:
        connection = _connect(store, ai_service, connection_id)
        if connection is None:
            return None

    st.sidebar.success("Подключение настроено")
    st.sidebar.caption(
        "ID рабочего каталога",
        help=(
            "Каталог Yandex Cloud, в котором выполняются запросы и создаются "
            "векторные индексы."
        ),
    )
    st.sidebar.code(connection.folder_id, language=None)
    if st.sidebar.button("Отключить ключ"):
        store.delete(connection_id)
        reset_chat(ai_service, connection_id)
        st.rerun()
    return connection


def _connect(
    store: ApiKeyStore,
    ai_service: AIInteractionService,
    connection_id: str,
) -> ApiKeyConnection | None:
    st.sidebar.caption(
        "Нужны API-ключ и ID каталога, в котором будут списываться расходы."
    )
    ai_studio_column, _ = st.sidebar.columns(2)
    with ai_studio_column:
        st.link_button("AI Studio (1)", AI_STUDIO_URL)
    _render_connection_guide()
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
            "AI Studio отклонил подключение. Проверьте ключ, каталог и роли "
            "сервисного аккаунта."
        )
        return None
    except ApiKeyStoreError:
        st.sidebar.error("Не удалось сохранить подключение.")
        return None
    reset_chat(ai_service, connection_id)
    st.rerun()
    return None


def _render_connection_guide() -> None:
    with st.sidebar.expander("Инструкция", expanded=False):
        st.caption("Ключ показывается только один раз.")
        st.markdown(
            "1. Переходите на сайт AI Studio (1) и нажмите на `Начать работу` или `Войти`.\n"
            "2. Выберите нужный каталог и скопируйте его ID, для этого наведите курсор "
            "на интерфейс выбора каталога и появится скрытая кнопка `ID`, при нажатии "
            "копирование произойдет автоматически.\n"
            "3. Возвращайтесь на страницу диалогового интерфейса и вставьте в поле "
            "`ID каталога`.\n"
            "4. Переходите на сайт AI Studio (1) и нажмите `Создать API-ключ`. "
            "Сразу скопируйте секретную часть ключа.\n"
            "5. Возвращайтесь на страницу диалогового интерфейса и вставьте в поле "
            "`API-ключ` в диалоговом интерфейсе.\n"
            "6. Когда оба поля заполнены, нажмите `Проверить и подключить`."
        )
        st.markdown(
            "Дополнительно можете воспользоваться официальной документацией:\n"
            f"[Инструкция по ключу]({API_KEY_GUIDE_URL}) · "
            f"[Где найти ID каталога]({FOLDER_ID_GUIDE_URL})"
        )


def reset_chat(ai_service: AIInteractionService, user_id: str) -> None:
    st.session_state.messages = []
    st.session_state.conversation_state = ConversationState()
    clear_agent_test_previews()
    _run_async(ai_service.reset_conversation(user_id))


def _run_async(awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)

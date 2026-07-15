from typing import Optional
from uuid import uuid4

import streamlit as st
from openai import OpenAIError
from openai.types.responses import ResponseInputParam

from ui.api_key_store import ApiKeyConnection, ApiKeyStoreError, EncryptedApiKeyStore
from config import WebUIConfig, load_web_ui_config
from context import get_api_key_client


st.set_page_config(page_title="AI Studio Chat", page_icon="AI", layout="centered")

AI_STUDIO_URL = "https://aistudio.yandex.ru/"
FOLDERS_CONSOLE_URL = "https://console.yandex.cloud/folders"
API_KEY_GUIDE_URL = (
    "https://aistudio.yandex.ru/docs/ru/ai-studio/operations/get-api-key.html"
)
FOLDER_ID_GUIDE_URL = (
    "https://yandex.cloud/ru/docs/resource-manager/operations/folder/get-id"
)


@st.cache_resource
def _load_services() -> tuple[WebUIConfig, EncryptedApiKeyStore]:
    config = load_web_ui_config()
    return config, EncryptedApiKeyStore(
        config.api_key_store.storage_path, config.api_key_store.encryption_key
    )


def _connection_id() -> str:
    if "connection_id" not in st.session_state:
        st.session_state.connection_id = f"web-{uuid4().hex}"
    return st.session_state.connection_id


def _reset_chat() -> None:
    st.session_state.messages = []


def _validate_connection(config: WebUIConfig, api_key: str, folder_id: str) -> None:
    client = get_api_key_client(api_key, folder_id, config.connection)
    client.responses.create(
        model=f"gpt://{folder_id}/{config.model.model_name}",
        input="Ответьте ровно: OK",
        max_output_tokens=2,
    )


def _render_connection(
    config: WebUIConfig, store: EncryptedApiKeyStore, connection_id: str
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
                _validate_connection(config, api_key, folder_id)
            store.save(connection_id, api_key, folder_id)
        except OpenAIError:
            st.sidebar.error(
                "AI Studio отклонил подключение. Проверьте ключ, каталог и роли сервисного аккаунта."
            )
            return None
        except ApiKeyStoreError:
            st.sidebar.error("Не удалось сохранить подключение.")
            return None
        _reset_chat()
        st.rerun()

    st.sidebar.success("Подключение настроено")
    st.sidebar.code(connection.folder_id, language=None)
    if st.sidebar.button("Отключить ключ"):
        store.delete(connection_id)
        _reset_chat()
        st.rerun()
    return connection


def _answer(
    config: WebUIConfig,
    connection: ApiKeyConnection,
    messages: ResponseInputParam,
) -> str:
    client = get_api_key_client(
        connection.api_key, connection.folder_id, config.connection
    )
    response = client.responses.create(
        model=f"gpt://{connection.folder_id}/{config.model.model_name}",
        input=messages,
    )
    return response.output_text


def main() -> None:
    st.title("AI Studio Chat")
    st.caption("Запросы выполняются в каталоге, связанном с вашим API-ключом.")

    config, store = _load_services()
    connection = _render_connection(config, store, _connection_id())

    if "messages" not in st.session_state:
        _reset_chat()
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Введите сообщение", disabled=connection is None)
    if not prompt or connection is None:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Генерируется ответ..."):
            try:
                answer = _answer(config, connection, st.session_state.messages)
            except OpenAIError:
                answer = "AI Studio отклонил запрос. Проверьте ключ, каталог и права."
            except Exception:
                answer = "Не удалось выполнить запрос к AI Studio. Повторите попытку."
            st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()

from uuid import uuid4

import streamlit as st

from ai_studio_agent_builder.config import load_web_ui_config
from ai_studio_agent_builder.infrastructure.persistence.api_key_store import (
    EncryptedApiKeyStore,
)
from ai_studio_agent_builder.infrastructure.observability.logging import (
    configure_console_logging,
)
from ai_interaction_service import AIInteractionService
from ui.chat_flow import render_chat
from ui.connection import render_connection
from ui.user_guidance import render_next_steps_sidebar
from ui.uploads import (
    attachment_record as _attachment_record,
    validate_uploaded_files as _validate_uploaded_files,
)


__all__ = ["_attachment_record", "_validate_uploaded_files", "main"]


st.set_page_config(page_title="AI Studio Chat", page_icon="AI", layout="centered")


@st.cache_resource
def _load_services() -> tuple[EncryptedApiKeyStore, AIInteractionService]:
    config = load_web_ui_config()
    return (
        EncryptedApiKeyStore(
            config.api_key_store.storage_path, config.api_key_store.encryption_key
        ),
        AIInteractionService(config.ai_service),
    )


def _connection_id() -> str:
    if "connection_id" not in st.session_state:
        st.session_state.connection_id = f"web-{uuid4().hex}"
    return st.session_state.connection_id


def main() -> None:
    st.title("AI Studio Chat")
    st.caption("Запросы выполняются в каталоге, связанном с вашим API-ключом.")
    st.caption(
        "Для RAG приложите несколько файлов и напишите: «Создай индекс из файлов»."
    )

    store, ai_service = _load_services()
    connection_id = _connection_id()
    connection = render_connection(store, ai_service, connection_id)
    render_next_steps_sidebar()
    render_chat(ai_service, connection, connection_id)


if __name__ == "__main__":
    configure_console_logging()
    main()

"""Top-level Streamlit view assembled from presentation controllers."""

import streamlit as st

from ai_studio_agent_builder.application.interaction import AIInteraction
from ai_studio_agent_builder.application.ports.api_key_store import ApiKeyStore

from .chat_flow import render_chat
from .connection import render_connection
from .user_guidance import render_next_steps_sidebar


def render_app(
    store: ApiKeyStore,
    ai_service: AIInteraction,
    connection_id: str,
) -> None:
    """Render the web UI using services supplied by the composition root."""

    st.title("AI Studio Chat")
    st.caption("Запросы выполняются в каталоге, связанном с вашим API-ключом.")
    st.caption(
        "Для RAG приложите несколько файлов и напишите: «Создай индекс из файлов»."
    )

    connection = render_connection(store, ai_service, connection_id)
    render_next_steps_sidebar()
    render_chat(ai_service, connection, connection_id)


__all__ = ["render_app"]

"""Thin executable bootstrap for the supported Streamlit UI."""

from uuid import uuid4

import streamlit as st

from ai_studio_agent_builder.composition import (
    WebServices,
    build_web_services,
    configure_web_logging,
)
from ai_studio_agent_builder.presentation.streamlit.app import render_app


@st.cache_resource
def _load_services() -> WebServices:
    return build_web_services()


def _connection_id() -> str:
    if "connection_id" not in st.session_state:
        st.session_state.connection_id = f"web-{uuid4().hex}"
    return st.session_state.connection_id


def main() -> None:
    st.set_page_config(page_title="AI Studio Chat", page_icon="AI", layout="centered")
    services = _load_services()
    render_app(
        services.api_key_store,
        services.ai_interaction,
        _connection_id(),
    )


if __name__ == "__main__":
    configure_web_logging()
    main()

"""Composition root for concrete runtime services and adapters."""

from dataclasses import dataclass

from ai_interaction_service import AIInteractionService

from .config import load_web_ui_config
from .infrastructure.observability.logging import configure_console_logging
from .infrastructure.persistence.api_key_store import EncryptedApiKeyStore


@dataclass(frozen=True)
class WebServices:
    """Concrete services required by the supported Streamlit runtime."""

    api_key_store: EncryptedApiKeyStore
    ai_interaction: AIInteractionService


def build_web_services() -> WebServices:
    """Build the Streamlit dependency graph from validated configuration."""

    config = load_web_ui_config()
    return WebServices(
        api_key_store=EncryptedApiKeyStore(
            config.api_key_store.storage_path,
            config.api_key_store.encryption_key,
        ),
        ai_interaction=AIInteractionService(config.ai_service),
    )


def configure_web_logging() -> None:
    """Configure logging for the executable web runtime."""

    configure_console_logging()


__all__ = ["WebServices", "build_web_services", "configure_web_logging"]

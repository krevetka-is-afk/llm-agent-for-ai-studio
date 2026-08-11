"""Compatibility imports for packaged credential DTOs and client factories.

New code must import application DTOs and the Yandex infrastructure factory
directly. This module is removed before the public ``v0.1.0`` release.
"""

from ai_studio_agent_builder.application.dto import (
    AIStudioCredentials,
    UserCredentials,
)
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.client_factory import (
    get_api_key_client,
    get_async_api_key_client,
)

__all__ = [
    "AIStudioCredentials",
    "UserCredentials",
    "get_api_key_client",
    "get_async_api_key_client",
]

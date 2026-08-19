from typing import Protocol

from openai import AsyncOpenAI, OpenAI

from ...application.dto import AIStudioCredentials


class ConnectionSettings(Protocol):
    base_url: str
    timeout: float


def get_api_key_client(
    credentials: AIStudioCredentials,
    connection_config: ConnectionSettings,
) -> OpenAI:
    return OpenAI(
        api_key=credentials.api_key,
        project=credentials.folder_id,
        base_url=connection_config.base_url,
        timeout=connection_config.timeout,
        default_headers={"Authorization": f"Api-Key {credentials.api_key}"},
    )


def get_async_api_key_client(
    credentials: AIStudioCredentials,
    connection_config: ConnectionSettings,
) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=credentials.api_key,
        project=credentials.folder_id,
        base_url=connection_config.base_url,
        timeout=connection_config.timeout,
        default_headers={"Authorization": f"Api-Key {credentials.api_key}"},
    )

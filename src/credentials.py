from dataclasses import dataclass

from openai import AsyncOpenAI, OpenAI

from config import ConnectionConfig


@dataclass(frozen=True)
class AIStudioCredentials:
    api_key: str
    folder_id: str


@dataclass(frozen=True)
class UserCredentials:
    """Legacy OAuth gateway contract kept outside the manual API-key flow."""

    access_token: str
    folder_id: str


def get_api_key_client(
    credentials: AIStudioCredentials, connection_config: ConnectionConfig
) -> OpenAI:
    return OpenAI(
        api_key=credentials.api_key,
        project=credentials.folder_id,
        base_url=connection_config.base_url,
        timeout=connection_config.timeout,
        default_headers={"Authorization": f"Api-Key {credentials.api_key}"},
    )


def get_async_api_key_client(
    credentials: AIStudioCredentials, connection_config: ConnectionConfig
) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=credentials.api_key,
        project=credentials.folder_id,
        base_url=connection_config.base_url,
        timeout=connection_config.timeout,
        default_headers={"Authorization": f"Api-Key {credentials.api_key}"},
    )

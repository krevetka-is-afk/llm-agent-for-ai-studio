"""Immutable runtime settings consumed by application and adapter layers."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    telegram_proxy_url: str | None


@dataclass(frozen=True)
class ModelConfig:
    model_name: str
    temperature: float
    max_output_tokens: int
    base_url: str
    sessions_db_path: Path
    verbosity: Literal["low", "medium", "high"] | None = None
    max_retries: int | None = None
    max_turns: int = 20


@dataclass(frozen=True)
class AgentRuntimeConfig:
    model_name: str
    temperature: float
    max_output_tokens: int

    def __post_init__(self) -> None:
        if not self.model_name.strip():
            raise ValueError("generated agent model_name must not be empty")
        if not 0 <= self.temperature <= 1:
            raise ValueError("generated agent temperature must be between 0 and 1")
        if not 1 <= self.max_output_tokens <= 4096:
            raise ValueError(
                "generated agent max_output_tokens must be between 1 and 4096"
            )


@dataclass(frozen=True)
class PathConfig:
    uploaded_files_dir: Path


@dataclass(frozen=True)
class SessionDBConfig:
    path: Path


@dataclass(frozen=True)
class ConnectionConfig:
    base_url: str
    timeout: float


@dataclass(frozen=True)
class ApiKeyStoreConfig:
    encryption_key: str
    storage_path: Path


@dataclass(frozen=True)
class AIServiceConfig:
    paths: PathConfig
    connection: ConnectionConfig
    session_db_config: SessionDBConfig
    rag_model: ModelConfig
    one_prompt: ModelConfig
    consultant: ModelConfig
    generated_agent_runtime: AgentRuntimeConfig


@dataclass(frozen=True)
class AppConfig:
    bot: BotConfig
    ai_service: AIServiceConfig


@dataclass(frozen=True)
class WebUIConfig:
    ai_service: AIServiceConfig
    api_key_store: ApiKeyStoreConfig


__all__ = [
    "AIServiceConfig",
    "AgentRuntimeConfig",
    "ApiKeyStoreConfig",
    "AppConfig",
    "BotConfig",
    "ConnectionConfig",
    "ModelConfig",
    "PathConfig",
    "SessionDBConfig",
    "WebUIConfig",
]

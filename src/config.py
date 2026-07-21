import os
import yaml

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Literal
from urllib.parse import urlparse


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


@dataclass(frozen=True)
class AppConfig:
    bot: BotConfig
    ai_service: AIServiceConfig


@dataclass(frozen=True)
class WebUIConfig:
    ai_service: AIServiceConfig
    api_key_store: ApiKeyStoreConfig


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    bot = BotConfig(
        bot_token=_required_env("BOT_TOKEN"),
        telegram_proxy_url=_optional_http_proxy_url("TELEGRAM_PROXY_URL"),
    )
    paths = PathConfig(
        uploaded_files_dir=_path_from_env_or_config(
            "UPLOADED_FILES_DIR", raw, "paths", "uploaded_files_dir"
        ),
    )

    session_db_path = _path_from_env_or_config(
        "CONVERSATION_DB_PATH", raw, "session_db", "path"
    )
    session_db = SessionDBConfig(
        path=session_db_path,
    )

    connection = ConnectionConfig(
        base_url=_safe_get(raw, "client", "base_url"),
        timeout=_safe_get(raw, "client", "timeout"),
    )

    models = _parse_models(_safe_get(raw, "models"), session_db_path)

    return AppConfig(
        bot=bot,
        ai_service=AIServiceConfig(
            paths=paths,
            connection=connection,
            session_db_config=session_db,
            rag_model=_safe_get(models, "rag_model"),
            one_prompt=_safe_get(models, "one_prompt"),
            consultant=_safe_get(models, "consultant"),
        ),
    )


def load_web_ui_config(path: str | Path = "config.yaml") -> WebUIConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    session_db_path = _path_from_env_or_config(
        "CONVERSATION_DB_PATH", raw, "session_db", "path"
    )
    models = _parse_models(_safe_get(raw, "models"), session_db_path)
    return WebUIConfig(
        ai_service=AIServiceConfig(
            paths=PathConfig(
                uploaded_files_dir=_path_from_env_or_config(
                    "UPLOADED_FILES_DIR", raw, "paths", "uploaded_files_dir"
                )
            ),
            connection=ConnectionConfig(
                base_url=_safe_get(raw, "client", "base_url"),
                timeout=_safe_get(raw, "client", "timeout"),
            ),
            session_db_config=SessionDBConfig(path=session_db_path),
            rag_model=_safe_get(models, "rag_model"),
            one_prompt=_safe_get(models, "one_prompt"),
            consultant=_safe_get(models, "consultant"),
        ),
        api_key_store=_load_api_key_store_config(),
    )


def _safe_get(src: Dict[str, Any], *keys: str, default_value=None) -> Any:
    value = src
    for key in keys:
        if not isinstance(value, dict):
            raise TypeError(f"Failed to get {key} from {value}, {value} is not dict")
        value = value.get(key)
        if value is None:
            if default_value is None:
                raise ValueError(f"Config file doesn't have key '{key}'")
            return default_value
    return value


def _path_from_env_or_config(
    env_name: str, raw: Dict[str, Any], *config_keys: str
) -> Path:
    return Path(os.getenv(env_name) or _safe_get(raw, *config_keys)).resolve()


def _parse_models(
    models_list: list, default_session_db_path: str | Path | None = None
) -> dict[str, ModelConfig]:
    parsed = {}

    for item in models_list:
        model_key = next((k for k, v in item.items() if v is None), None)
        if model_key is None:
            raise ValueError(f"Cannot find model key in: {item}")

        parsed[model_key] = ModelConfig(
            model_name=_safe_get(item, "model_name"),
            temperature=_safe_get(item, "temperature"),
            max_output_tokens=_safe_get(item, "max_output_tokens"),
            base_url=_safe_get(item, "base_url"),
            sessions_db_path=Path(
                _safe_get(
                    item, "session_db_path", default_value=default_session_db_path
                )
            ).resolve(),
            max_turns=_safe_get(item, "max_turns", default_value=20),
        )

    return parsed


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_http_proxy_url(name: str) -> str | None:
    value = os.getenv(name)
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError(f"{name} must be an HTTP or HTTPS proxy URL")
    return value


def _load_api_key_store_config() -> ApiKeyStoreConfig:
    required_names = ("YC_API_KEY_ENCRYPTION_KEY",)
    values = {name: os.getenv(name) for name in required_names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Incomplete API key storage configuration; missing: " + ", ".join(missing)
        )
    return ApiKeyStoreConfig(
        encryption_key=_required_value(values, "YC_API_KEY_ENCRYPTION_KEY"),
        storage_path=Path(os.getenv("YC_API_KEY_DB_PATH", "yc_api_keys.db")).resolve(),
    )


def _required_value(values: dict[str, str | None], name: str) -> str:
    value = values[name]
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

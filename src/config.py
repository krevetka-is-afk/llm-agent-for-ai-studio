import os
import yaml

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Literal


@dataclass(frozen=True)
class BotConfig:
    bot_token: str


@dataclass
class AIStudioAuth:
    api_key: str
    folder_id: str


@dataclass(frozen=True)
class ModelConfig:
    model_name: str
    temperature: float
    max_output_tokens: int
    base_url: str
    sessions_db_path: Path
    verbosity: Literal['low', 'medium', 'high'] | None = None
    max_retries: int | None = None


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
class AppConfig:
    auth: AIStudioAuth
    bot: BotConfig
    paths: PathConfig
    connection: ConnectionConfig
    session_db_config: SessionDBConfig
    rag_model: ModelConfig
    one_prompt: ModelConfig
    consultant: ModelConfig


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    bot = BotConfig(_required_env("BOT_TOKEN"))
    auth = AIStudioAuth(
        api_key=_required_env("YANDEX_API_KEY"),
        folder_id=_required_env("YANDEX_FOLDER_ID"),
    )

    paths = PathConfig(
        uploaded_files_dir=Path(_safe_get(raw, "paths", "uploaded_files_dir")).resolve(),
    )

    session_db_path = _safe_get(raw, "session_db", "path")
    session_db = SessionDBConfig(
        path=Path(session_db_path).resolve(),
    )

    connection = ConnectionConfig(
        base_url=_safe_get(raw, "client", "base_url"),
        timeout=_safe_get(raw, "client", "timeout"),
    )

    models = _parse_models(_safe_get(raw, "models"), session_db_path)

    return AppConfig(
        auth=auth,
        bot=bot,
        paths=paths,
        connection=connection,
        session_db_config=session_db,
        rag_model=_safe_get(models, "rag_model"),
        one_prompt=_safe_get(models, "one_prompt"),
        consultant=_safe_get(models, "consultant"),
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


def _parse_models(models_list: list, default_session_db_path: str | None = None) -> dict[str, ModelConfig]:
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
                _safe_get(item, "session_db_path", default_value=default_session_db_path)
            ).resolve(),
        )

    return parsed


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

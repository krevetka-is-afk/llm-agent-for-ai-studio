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
    api_token: str
    folder_id: str


@dataclass(frozen=True)
class ModelConfig:
    model_name: str
    temperature: float
    max_output_tokens: int
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
class AgentConfig:
    session_db: SessionDBConfig
    connection: ConnectionConfig
    model: ModelConfig
    auth: AIStudioAuth


@dataclass(frozen=True)
class AppConfig:
    bot: BotConfig
    paths: PathConfig
    connection: ConnectionConfig
    rag_model: AgentConfig
    one_prompt: AgentConfig
    consultant: AgentConfig


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    bot = BotConfig(_required_env("BOT_TOKEN"))
    auth = AIStudioAuth(
        api_token=_required_env("YANDEX_API_KEY"),
        folder_id=_required_env("YANDEX_FOLDER_ID"),
    )

    paths = PathConfig(
        uploaded_files_dir=Path(_safe_get(raw, "paths", "uploaded_files_dir").resolve())
    )

    session_db = SessionDBConfig(
        path=Path(_safe_get(raw, "session_db", "path")).resolve(),
    )

    connection = ConnectionConfig(
        base_url=_safe_get(raw, "client", "base_url"),
        timeout=_safe_get(raw, "client", "timeout"),
    )
    models = _parse_models(_safe_get(raw, "models"))

    rag_model = AgentConfig(
        session_db=session_db,
        connection=connection,
        model=_safe_get(models, "rag_model"),
        auth=auth,
    )

    one_prompt = AgentConfig(
        session_db=session_db,
        connection=connection,
        model=_safe_get(models, "one_prompt"),
        auth=auth,
    )

    consultant = AgentConfig(
        session_db=session_db,
        connection=connection,
        model=_safe_get(models, "consultant"),
        auth=auth,
    )

    return AppConfig(
        bot=bot,
        paths=paths,
        connection=connection,
        rag_model=rag_model,
        one_prompt=one_prompt,
        consultant=consultant,
    )


def _safe_get(src: Dict[str, Any], *keys: str) -> Any:
    value = src
    for key in keys:
        if not isinstance(value, dict):
            raise TypeError(f"Failed to get {key} from {value}, {value} is not dict")
        value = value.get(key)
        if value is None:
            raise ValueError(f"Config file doesn't have key '{key}'")
    return value


def _parse_models(models_list: list) -> dict[str, ModelConfig]:
    parsed = {}

    for item in models_list:
        model_key = next((k for k, v in item.items() if v is None), None)
        if model_key is None:
            raise ValueError(f"Cannot find model key in: {item}")

        parsed[model_key] = ModelConfig(
            model_name=_safe_get(item, "model_name"),
            temperature=_safe_get(item, "temperature"),
            max_output_tokens=_safe_get(item, "max_output_tokens"),
        )

    return parsed


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

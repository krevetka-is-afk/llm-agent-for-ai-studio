from pathlib import Path

import os
from dotenv import load_dotenv
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://ai.api.cloud.yandex.net/v1"


@dataclass(frozen=True)
class Settings:
    api_key: str
    folder_id: str
    model_uri: str
    base_url: str
    temperature: float
    max_output_tokens: int
    timeout: float

    @classmethod
    def load_settings(cls) -> Settings:

        load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)

        folder_id = _required_env("YANDEX_FOLDER_ID")
        model_uri = os.getenv("YANDEX_MODEL_URI")
        if not model_uri:
            model = _required_env("YANDEX_MODEL")
            model_uri = (
                model if model.startswith("gpt://") else f"gpt://{folder_id}/{model}"
            )

        return Settings(
            api_key=_required_env("YANDEX_API_KEY"),
            folder_id=folder_id,
            model_uri=model_uri,
            base_url=os.getenv("YANDEX_BASE_URL", DEFAULT_BASE_URL),
            temperature=_env_float("YANDEX_TEMPERATURE", default=0.5),
            max_output_tokens=_env_int("YANDEX_MAX_OUTPUT_TOKENS", default=1000),
            timeout=_env_float("YANDEX_TIMEOUT", default=36.6),
        )


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError as e:
        raise RuntimeError(
            f"Invalid environment variable: {name} must be int got {value} instead"
        ) from e


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as e:
        raise RuntimeError(
            f"Invalid environment variable: {name} must be float got {value} instead"
        ) from e

import logging
import json

from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path
from openai import OpenAI

from config import Settings

logger = logging.getLogger(__name__)


def get_user_client(
    user_api_key: str, user_folder_id: str, settings: Settings
) -> OpenAI:
    return OpenAI(
        api_key=user_api_key,
        project=user_folder_id,
        base_url=settings.base_url,
        timeout=settings.timeout,
    )


@dataclass
class UserSecrets:
    api_token: Optional[str] = None
    folder_id: Optional[str] = None


class UserSecretsStore:
    def __init__(self, storage_path: Optional[Path] = None):
        self._storage_path = storage_path
        self._data: dict[str, UserSecrets] = {}
        self._load()

    def get(self, user_id: str) -> UserSecrets:
        return self._data.setdefault(user_id, UserSecrets())

    def set_api_token(self, user_id: str, api_token: str) -> None:
        self.get(user_id).api_token = api_token
        self._save()

    def set_folder_id(self, user_id: str, folder_id: str) -> None:
        self.get(user_id).folder_id = folder_id
        self._save()

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return

        try:
            raw_data = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load user secrets from %s", self._storage_path)
            return

        if not isinstance(raw_data, dict):
            logger.warning("User secrets file has unexpected format: %s", self._storage_path)
            return

        for user_id, raw_secrets in raw_data.items():
            if not isinstance(user_id, str) or not isinstance(raw_secrets, dict):
                continue

            api_token = raw_secrets.get("api_token")
            folder_id = raw_secrets.get("folder_id")
            self._data[user_id] = UserSecrets(
                api_token=api_token if isinstance(api_token, str) else None,
                folder_id=folder_id if isinstance(folder_id, str) else None,
            )

    def _save(self) -> None:
        if self._storage_path is None:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._storage_path.with_name(f"{self._storage_path.name}.tmp")
        payload = {
            user_id: {
                "api_token": secrets.api_token,
                "folder_id": secrets.folder_id,
            }
            for user_id, secrets in self._data.items()
        }

        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.chmod(0o600)
        temp_path.replace(self._storage_path)
        self._storage_path.chmod(0o600)


@dataclass
class RequestContext:
    user_id: str
    user_files_dir: Path
    client: OpenAI
    session_is_done: bool = field(default=False, init=False)

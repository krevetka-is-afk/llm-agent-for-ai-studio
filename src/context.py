import logging

from collections import defaultdict
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
    def __init__(self):
        self._data: defaultdict[str, UserSecrets] = defaultdict(UserSecrets)

    def get(self, user_id: str) -> UserSecrets:
        return self._data[user_id]

    def set_api_token(self, user_id: str, api_token: str) -> None:
        self._data[user_id].api_token = api_token

    def set_folder_id(self, user_id: str, folder_id: str) -> None:
        self._data[user_id].folder_id = folder_id


@dataclass
class RequestContext:
    user_id: str
    user_files_dir: Path
    client: OpenAI
    session_is_done: bool = field(default=False, init=False)

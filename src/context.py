import logging

from collections import defaultdict
from typing import Optional
from dataclasses import dataclass
from pathlib import Path
from enum import Enum, auto
from openai import OpenAI

from config import ConnectionConfig

logger = logging.getLogger(__name__)


def get_user_client(
    user_api_key: str, user_folder_id: str, connection_config: ConnectionConfig
) -> OpenAI:
    return OpenAI(
        api_key=user_api_key,
        project=user_folder_id,
        base_url=connection_config.base_url,
        timeout=connection_config.timeout,
    )


class ConversationOptions(Enum):
    COORDINATOR = auto()
    RAG = auto()
    ONE_PROMPT = auto()


class ConversationState:
    def __init__(self):
        self.state = ConversationOptions.COORDINATOR

    def update_state(self, new_state: ConversationOptions):
        self.state = new_state

    def reset_state(self):
        self.state = ConversationOptions.COORDINATOR


@dataclass
class UserSecrets:
    api_token: Optional[str] = None
    folder_id: Optional[str] = None


class UserStore:
    def __init__(self):
        self._data: defaultdict[str, UserSecrets] = defaultdict(UserSecrets)
        self._conv: defaultdict[str, ConversationState] = defaultdict(ConversationState)

    def get(self, user_id: str) -> UserSecrets:
        return self._data[user_id]

    def get_state(self, user_id: str) -> ConversationState:
        return self._conv[user_id]

    def set_api_token(self, user_id: str, api_token: str) -> None:
        self._data[user_id].api_token = api_token

    def set_folder_id(self, user_id: str, folder_id: str) -> None:
        self._data[user_id].folder_id = folder_id


@dataclass
class RequestContext:
    user_id: str
    user_files_dir: Path
    client: OpenAI
    state: ConversationState

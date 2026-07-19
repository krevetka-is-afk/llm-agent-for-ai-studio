import logging

from collections import defaultdict
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum, auto
from openai import AsyncOpenAI, OpenAI

from config import ConnectionConfig

logger = logging.getLogger(__name__)


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


@dataclass
class PendingCredentials:
    api_token: Optional[str] = None
    folder_id: Optional[str] = None
    secret_message_ids: list[int] = field(default_factory=list)


class UserStore:
    def __init__(self):
        self._data: defaultdict[str, UserSecrets] = defaultdict(UserSecrets)
        self._pending: defaultdict[str, PendingCredentials] = defaultdict(
            PendingCredentials
        )
        self._conv: defaultdict[str, ConversationState] = defaultdict(ConversationState)

    def get(self, user_id: str) -> UserSecrets:
        return self._data[user_id]

    def get_state(self, user_id: str) -> ConversationState:
        return self._conv[user_id]

    def set_pending_api_token(
        self, user_id: str, api_token: str, message_id: int
    ) -> None:
        pending = self._pending[user_id]
        pending.api_token = api_token
        self._remember_secret_message(pending, message_id)

    def set_pending_folder_id(
        self, user_id: str, folder_id: str, message_id: int
    ) -> None:
        pending = self._pending[user_id]
        pending.folder_id = folder_id
        self._remember_secret_message(pending, message_id)

    def get_pending_credentials(self, user_id: str) -> AIStudioCredentials | None:
        pending = self._pending[user_id]
        if pending.api_token is None or pending.folder_id is None:
            return None
        return AIStudioCredentials(
            api_key=pending.api_token,
            folder_id=pending.folder_id,
        )

    def activate_pending_credentials(self, user_id: str) -> tuple[int, ...]:
        credentials = self.get_pending_credentials(user_id)
        if credentials is None:
            raise ValueError("Cannot activate incomplete credentials")
        self._data[user_id] = UserSecrets(
            api_token=credentials.api_key,
            folder_id=credentials.folder_id,
        )
        return self.clear_pending_message_ids(user_id)

    def clear_folder_id(self, user_id: str) -> None:
        secrets = self._data[user_id]
        secrets.folder_id = None

    def clear_pending_message_ids(self, user_id: str) -> tuple[int, ...]:
        pending = self._pending[user_id]
        message_ids = tuple(pending.secret_message_ids)
        self._pending[user_id] = PendingCredentials()
        return message_ids

    @staticmethod
    def _remember_secret_message(pending: PendingCredentials, message_id: int) -> None:
        if message_id not in pending.secret_message_ids:
            pending.secret_message_ids.append(message_id)


@dataclass
class RequestContext:
    user_id: str
    user_files_dir: Path
    client: OpenAI
    state: ConversationState
    api_key: str
    folder_id: str

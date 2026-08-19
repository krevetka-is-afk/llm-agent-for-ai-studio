import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from ...application.builder_state import ConversationState
from ...application.dto import AIStudioCredentials


DEFAULT_PENDING_CREDENTIAL_TTL_SECONDS = 5 * 60


@dataclass
class UserSecrets:
    api_token: str | None = None
    folder_id: str | None = None


@dataclass
class PendingCredentials:
    api_token: str | None = None
    folder_id: str | None = None
    secret_message_ids: list[int] = field(default_factory=list)
    expires_at: float | None = None


class UserStore:
    def __init__(
        self,
        *,
        pending_ttl_seconds: float = DEFAULT_PENDING_CREDENTIAL_TTL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if pending_ttl_seconds <= 0:
            raise ValueError("Pending credential TTL must be positive")
        self._pending_ttl_seconds = pending_ttl_seconds
        self._monotonic = monotonic
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
        pending = self._active_pending(user_id)
        pending.api_token = api_token
        self._remember_secret_message(pending, message_id)
        self._renew_pending(pending)

    def set_pending_folder_id(
        self, user_id: str, folder_id: str, message_id: int
    ) -> None:
        pending = self._active_pending(user_id)
        pending.folder_id = folder_id
        self._remember_secret_message(pending, message_id)
        self._renew_pending(pending)

    def get_pending_credentials(self, user_id: str) -> AIStudioCredentials | None:
        pending = self._active_pending(user_id)
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

    def clear_credentials(self, user_id: str) -> tuple[int, ...]:
        message_ids = self.clear_pending_message_ids(user_id)
        self._data.pop(user_id, None)
        self._conv.pop(user_id, None)
        return message_ids

    def clear_folder_id(self, user_id: str) -> None:
        self._data[user_id].folder_id = None

    def clear_pending_message_ids(self, user_id: str) -> tuple[int, ...]:
        pending = self._pending[user_id]
        message_ids = tuple(pending.secret_message_ids)
        self._pending[user_id] = PendingCredentials()
        return message_ids

    def _active_pending(self, user_id: str) -> PendingCredentials:
        pending = self._pending[user_id]
        if pending.expires_at is not None and self._monotonic() >= pending.expires_at:
            pending.api_token = None
            pending.folder_id = None
            pending.expires_at = None
        return pending

    def _renew_pending(self, pending: PendingCredentials) -> None:
        pending.expires_at = self._monotonic() + self._pending_ttl_seconds

    @staticmethod
    def _remember_secret_message(pending: PendingCredentials, message_id: int) -> None:
        if message_id not in pending.secret_message_ids:
            pending.secret_message_ids.append(message_id)


__all__ = [
    "DEFAULT_PENDING_CREDENTIAL_TTL_SECONDS",
    "PendingCredentials",
    "UserSecrets",
    "UserStore",
]

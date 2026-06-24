import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from openai import AsyncOpenAI


@dataclass(frozen=True)
class PendingConnection:
    state: str
    telegram_user_id: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None


@dataclass(frozen=True)
class ConnectedYandexCloud:
    folder_id_masked: str
    api_key_masked: str


class ConnectionStateError(Exception):
    pass


class UnknownConnectionState(ConnectionStateError):
    pass


class ExpiredConnectionState(ConnectionStateError):
    pass


class UsedConnectionState(ConnectionStateError):
    pass


class ConnectionStateUserMismatch(ConnectionStateError):
    pass


class InvalidYandexCloudCredentials(Exception):
    pass


class UserSecretsWriter(Protocol):
    def set_api_token(self, user_id: str, api_token: str) -> None:
        ...

    def set_folder_id(self, user_id: str, folder_id: str) -> None:
        ...


class CredentialsVerifier(Protocol):
    async def verify(
        self,
        *,
        api_token: str,
        folder_id: str,
        base_url: str,
        timeout: float,
    ) -> None:
        ...


class ConnectionStateStore:
    def __init__(self, ttl_seconds: int):
        self._ttl = timedelta(seconds=ttl_seconds)
        self._states: dict[str, PendingConnection] = {}

    def create(self, telegram_user_id: str) -> PendingConnection:
        now = datetime.now(timezone.utc)
        state = secrets.token_urlsafe(32)
        pending = PendingConnection(
            state=state,
            telegram_user_id=telegram_user_id,
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._states[state] = pending
        self._cleanup(now)
        return pending

    def validate(self, state: str, telegram_user_id: str) -> PendingConnection:
        now = datetime.now(timezone.utc)
        pending = self._states.get(state)
        if pending is None:
            raise UnknownConnectionState("Unknown connection state")
        if pending.used_at is not None:
            raise UsedConnectionState("Connection state already used")
        if pending.expires_at <= now:
            raise ExpiredConnectionState("Connection state expired")
        if pending.telegram_user_id != telegram_user_id:
            raise ConnectionStateUserMismatch("Connection state belongs to another user")
        return pending

    def mark_used(self, state: str) -> None:
        pending = self._states.get(state)
        if pending is None:
            raise UnknownConnectionState("Unknown connection state")
        self._states[state] = PendingConnection(
            state=pending.state,
            telegram_user_id=pending.telegram_user_id,
            created_at=pending.created_at,
            expires_at=pending.expires_at,
            used_at=datetime.now(timezone.utc),
        )

    def _cleanup(self, now: datetime) -> None:
        expired_states = [
            state
            for state, pending in self._states.items()
            if pending.expires_at <= now and pending.used_at is None
        ]
        for state in expired_states:
            del self._states[state]


class OpenAIYandexCloudCredentialsVerifier:
    async def verify(
        self,
        *,
        api_token: str,
        folder_id: str,
        base_url: str,
        timeout: float,
    ) -> None:
        client = AsyncOpenAI(
            api_key=api_token,
            project=folder_id,
            base_url=base_url,
            timeout=timeout,
        )
        try:
            await client.models.list()
        except Exception as exc:
            raise InvalidYandexCloudCredentials(
                "Failed to verify Yandex Cloud credentials"
            ) from exc
        finally:
            await client.close()


class YandexCloudConnector:
    def __init__(
        self,
        *,
        state_store: ConnectionStateStore,
        user_store: UserSecretsWriter,
        verifier: CredentialsVerifier,
        base_url: str,
        verify_timeout: float,
    ):
        self._state_store = state_store
        self._user_store = user_store
        self._verifier = verifier
        self._base_url = base_url
        self._verify_timeout = verify_timeout

    async def connect(
        self,
        *,
        telegram_user_id: str,
        state: str,
        folder_id: str,
        api_token: str,
    ) -> ConnectedYandexCloud:
        folder_id = validate_folder_id(folder_id)
        api_token = validate_api_token(api_token)
        self._state_store.validate(state, telegram_user_id)

        await self._verifier.verify(
            api_token=api_token,
            folder_id=folder_id,
            base_url=self._base_url,
            timeout=self._verify_timeout,
        )

        self._user_store.set_folder_id(telegram_user_id, folder_id)
        self._user_store.set_api_token(telegram_user_id, api_token)
        self._state_store.mark_used(state)

        return ConnectedYandexCloud(
            folder_id_masked=mask_folder_id(folder_id),
            api_key_masked=mask_api_key(api_token),
        )


def validate_folder_id(folder_id: str) -> str:
    value = folder_id.strip()
    if not value:
        raise ValueError("folder_id is empty")
    if len(value) > 128:
        raise ValueError("folder_id is too long")
    return value


def validate_api_token(api_token: str) -> str:
    value = api_token.strip()
    if not value:
        raise ValueError("api_token is empty")
    if len(value) > 4096:
        raise ValueError("api_token is too long")
    return value


def mask_folder_id(folder_id: str) -> str:
    if len(folder_id) <= 6:
        return folder_id[:2] + "***"
    return folder_id[:3] + "*" * max(3, len(folder_id) - 6) + folder_id[-3:]


def mask_api_key(api_token: str) -> str:
    if len(api_token) <= 6:
        return "****"
    return "****" + api_token[-6:]

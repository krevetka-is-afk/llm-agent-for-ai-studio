"""Application contract for user-scoped AI Studio API-key persistence."""

from dataclasses import dataclass
from typing import Protocol


class ApiKeyStoreError(Exception):
    """Raised when a stored connection cannot be read or persisted safely."""


@dataclass(frozen=True)
class ApiKeyConnection:
    """Decrypted connection data returned to an application caller."""

    api_key: str
    folder_id: str


class ApiKeyStore(Protocol):
    """Persist encrypted connection data behind an application-owned boundary."""

    def save(self, connection_id: str, api_key: str, folder_id: str) -> None: ...

    def get(self, connection_id: str) -> ApiKeyConnection | None: ...

    def delete(self, connection_id: str) -> None: ...


__all__ = ["ApiKeyConnection", "ApiKeyStore", "ApiKeyStoreError"]

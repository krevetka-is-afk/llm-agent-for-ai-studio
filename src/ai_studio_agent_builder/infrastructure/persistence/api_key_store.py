import os
import sqlite3
import stat
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from ai_studio_agent_builder.application.ports.api_key_store import (
    ApiKeyConnection,
    ApiKeyStoreError,
)


DEFAULT_API_KEY_RETENTION_SECONDS = 30 * 24 * 60 * 60


class EncryptedApiKeyStore:
    """Store UI-provided AI Studio API keys encrypted at rest."""

    def __init__(
        self,
        path: Path,
        encryption_key: str,
        *,
        retention_seconds: int = DEFAULT_API_KEY_RETENTION_SECONDS,
    ):
        if retention_seconds <= 0:
            raise ValueError("API key retention must be positive")
        try:
            self._fernet = Fernet(encryption_key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "YC_API_KEY_ENCRYPTION_KEY must be a URL-safe base64 Fernet key"
            ) from exc
        self._path = path
        self._retention_seconds = retention_seconds
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600, exist_ok=True)
        self._restrict_permissions()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _restrict_permissions(self) -> None:
        if os.name == "posix":
            self._path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS api_key_connections (
                    connection_id TEXT PRIMARY KEY,
                    api_key_enc TEXT NOT NULL,
                    folder_id TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            self._purge_expired(connection)

    def _purge_expired(self, connection: sqlite3.Connection) -> None:
        cutoff = int(time.time()) - self._retention_seconds
        connection.execute(
            "DELETE FROM api_key_connections WHERE updated_at < ?",
            (cutoff,),
        )

    def save(self, connection_id: str, api_key: str, folder_id: str) -> None:
        encrypted_key = self._fernet.encrypt(api_key.encode("utf-8")).decode("ascii")
        with self._connect() as connection:
            self._purge_expired(connection)
            connection.execute(
                """
                INSERT INTO api_key_connections(connection_id, api_key_enc, folder_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(connection_id) DO UPDATE SET
                    api_key_enc = excluded.api_key_enc,
                    folder_id = excluded.folder_id,
                    updated_at = excluded.updated_at
                """,
                (connection_id, encrypted_key, folder_id, int(time.time())),
            )

    def get(self, connection_id: str) -> ApiKeyConnection | None:
        with self._connect() as connection:
            self._purge_expired(connection)
            row = connection.execute(
                """
                SELECT api_key_enc, folder_id
                FROM api_key_connections
                WHERE connection_id = ?
                """,
                (connection_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            api_key = self._fernet.decrypt(row[0].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ApiKeyStoreError("Stored API key cannot be decrypted") from exc
        return ApiKeyConnection(api_key=api_key, folder_id=row[1])

    def delete(self, connection_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM api_key_connections WHERE connection_id = ?",
                (connection_id,),
            )


__all__ = [
    "ApiKeyConnection",
    "ApiKeyStoreError",
    "DEFAULT_API_KEY_RETENTION_SECONDS",
    "EncryptedApiKeyStore",
]

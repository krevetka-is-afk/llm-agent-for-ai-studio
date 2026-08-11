import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class ApiKeyStoreError(Exception):
    pass


@dataclass(frozen=True)
class ApiKeyConnection:
    api_key: str
    folder_id: str


class EncryptedApiKeyStore:
    """Store UI-provided AI Studio API keys encrypted at rest."""

    def __init__(self, path: Path, encryption_key: str):
        try:
            self._fernet = Fernet(encryption_key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "YC_API_KEY_ENCRYPTION_KEY must be a URL-safe base64 Fernet key"
            ) from exc
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

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

    def save(self, connection_id: str, api_key: str, folder_id: str) -> None:
        encrypted_key = self._fernet.encrypt(api_key.encode("utf-8")).decode("ascii")
        with self._connect() as connection:
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


__all__ = ["ApiKeyConnection", "ApiKeyStoreError", "EncryptedApiKeyStore"]

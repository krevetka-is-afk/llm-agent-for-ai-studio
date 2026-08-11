import sqlite3
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class CredentialStoreError(Exception):
    pass


class EncryptedCredentialStore:
    """Stores only encrypted long-lived refresh tokens for the OAuth prototype."""

    def __init__(self, path: Path, encryption_key: str):
        try:
            self._fernet = Fernet(encryption_key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "YC_TOKEN_ENCRYPTION_KEY must be a URL-safe base64 Fernet key"
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
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    subject_id TEXT PRIMARY KEY,
                    refresh_token_enc TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )

    def save_refresh_token(self, subject_id: str, refresh_token: str) -> None:
        encrypted = self._fernet.encrypt(refresh_token.encode("utf-8")).decode("ascii")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO refresh_tokens(subject_id, refresh_token_enc, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(subject_id) DO UPDATE SET
                    refresh_token_enc = excluded.refresh_token_enc,
                    updated_at = excluded.updated_at
                """,
                (subject_id, encrypted, int(time.time())),
            )

    def get_refresh_token(self, subject_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT refresh_token_enc FROM refresh_tokens WHERE subject_id = ?",
                (subject_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            return self._fernet.decrypt(row[0].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise CredentialStoreError(
                "Stored refresh token cannot be decrypted"
            ) from exc

    def delete_refresh_token(self, subject_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM refresh_tokens WHERE subject_id = ?", (subject_id,)
            )

    def has_refresh_token(self, subject_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM refresh_tokens WHERE subject_id = ?", (subject_id,)
            ).fetchone()
        return row is not None

import os
import sqlite3
import stat

import pytest

from cryptography.fernet import Fernet

from ai_studio_agent_builder.infrastructure.persistence.api_key_store import (
    EncryptedApiKeyStore,
)


def test_api_key_store_encrypts_key_and_deletes_connection(tmp_path) -> None:
    path = tmp_path / "api_keys.db"
    store = EncryptedApiKeyStore(path, Fernet.generate_key().decode("ascii"))

    store.save("web-session", "AQAAAA-secret-api-key", "b1gfolder")

    connection = store.get("web-session")
    assert connection is not None
    assert connection.api_key == "AQAAAA-secret-api-key"
    assert connection.folder_id == "b1gfolder"
    with sqlite3.connect(path) as database:
        stored_value = database.execute(
            "SELECT api_key_enc FROM api_key_connections"
        ).fetchone()
    assert stored_value is not None
    assert "AQAAAA-secret-api-key" not in stored_value[0]

    store.delete("web-session")

    assert store.get("web-session") is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode unavailable")
def test_api_key_store_restricts_database_permissions(tmp_path) -> None:
    path = tmp_path / "api_keys.db"

    EncryptedApiKeyStore(path, Fernet.generate_key().decode("ascii"))

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_api_key_store_purges_expired_connections(tmp_path) -> None:
    path = tmp_path / "api_keys.db"
    store = EncryptedApiKeyStore(
        path,
        Fernet.generate_key().decode("ascii"),
        retention_seconds=60,
    )
    store.save("abandoned-session", "AQAAAA-secret-api-key", "b1gfolder")
    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE api_key_connections SET updated_at = 0 WHERE connection_id = ?",
            ("abandoned-session",),
        )

    assert store.get("abandoned-session") is None

import sqlite3

from cryptography.fernet import Fernet

from ui.api_key_store import EncryptedApiKeyStore


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

import base64
import hashlib
import sqlite3
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

from experimental.oauth.config import OAuthGatewayConfig
from experimental.oauth.credential_store import EncryptedCredentialStore
from experimental.oauth.gateway import (
    GatewayInvalidState,
    OAuthFolder,
    OAuthGateway,
    OAuthTokens,
)


class FakeRemoteClient:
    def __init__(self, *, expires_in: int = 3600):
        self.expires_in = expires_in
        self.exchange_calls: list[tuple[str, str]] = []
        self.refresh_calls: list[str] = []
        self.revoked_tokens: list[str] = []
        self.folders = (
            OAuthFolder(
                id="folder-a",
                name="development",
                cloud_id="cloud-a",
                cloud_name="team-cloud",
            ),
        )

    def exchange_code(self, code: str, code_verifier: str) -> OAuthTokens:
        self.exchange_calls.append((code, code_verifier))
        return OAuthTokens("iam-initial", "refresh-secret", self.expires_in)

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        self.refresh_calls.append(refresh_token)
        return OAuthTokens("iam-refreshed", "refresh-rotated", 3600)

    def list_folders(self, access_token: str) -> tuple[OAuthFolder, ...]:
        assert access_token in {"iam-initial", "iam-refreshed"}
        return self.folders

    def revoke(self, refresh_token: str) -> None:
        self.revoked_tokens.append(refresh_token)


def _gateway(tmp_path, *, expires_in: int = 3600):
    config = OAuthGatewayConfig(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://gateway.example/yc/oauth/callback",
        encryption_key=Fernet.generate_key().decode("ascii"),
        storage_path=tmp_path / "refresh_tokens.db",
        callback_host="127.0.0.1",
        callback_port=8080,
        scopes=("openid", "profile", "email"),
        shared_secret="internal-secret",
    )
    remote = FakeRemoteClient(expires_in=expires_in)
    store = EncryptedCredentialStore(config.storage_path, config.encryption_key)
    return OAuthGateway(config, store, remote), remote, config


def test_gateway_uses_pkce_and_credential_store_holds_only_refresh_token(
    tmp_path,
) -> None:
    gateway, remote, config = _gateway(tmp_path)

    authorization_url = gateway.begin_authorization("telegram-user")
    query = parse_qs(urlparse(authorization_url).query)
    gateway.complete_authorization("authorization-code", query["state"][0])

    _, code_verifier = remote.exchange_calls[0]
    expected_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert query["code_challenge"] == [expected_challenge]
    assert query["scope"] == ["openid profile email"]
    assert gateway.is_connected("telegram-user") is True

    with sqlite3.connect(config.storage_path) as database:
        columns = database.execute("PRAGMA table_info(refresh_tokens)").fetchall()
        stored_token = database.execute(
            "SELECT refresh_token_enc FROM refresh_tokens"
        ).fetchone()
    assert [column[1] for column in columns] == [
        "subject_id",
        "refresh_token_enc",
        "updated_at",
    ]
    assert stored_token is not None
    assert "refresh-secret" not in stored_token[0]

    with pytest.raises(GatewayInvalidState):
        gateway.complete_authorization("authorization-code", query["state"][0])


def test_gateway_refreshes_iam_token_and_rotates_refresh_token(tmp_path) -> None:
    gateway, remote, _ = _gateway(tmp_path, expires_in=1)
    state = parse_qs(urlparse(gateway.begin_authorization("telegram-user")).query)[
        "state"
    ][0]
    gateway.complete_authorization("authorization-code", state)

    assert gateway.get_iam_token("telegram-user") == "iam-refreshed"
    assert remote.refresh_calls == ["refresh-secret"]


def test_gateway_validates_folders_and_revokes_on_disconnect(tmp_path) -> None:
    gateway, remote, _ = _gateway(tmp_path)
    state = parse_qs(urlparse(gateway.begin_authorization("telegram-user")).query)[
        "state"
    ][0]
    gateway.complete_authorization("authorization-code", state)

    gateway.validate_folder("telegram-user", "folder-a")
    gateway.disconnect("telegram-user")

    assert remote.revoked_tokens == ["refresh-secret"]
    assert gateway.is_connected("telegram-user") is False

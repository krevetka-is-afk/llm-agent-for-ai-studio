import base64
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import OAuthGatewayConfig
from .credential_store import CredentialStoreError, EncryptedCredentialStore

logger = logging.getLogger(__name__)

AUTHORIZATION_ENDPOINT = "https://auth.yandex.cloud/oauth/authorize"
TOKEN_ENDPOINT = "https://auth.yandex.cloud/oauth/token"
REVOCATION_ENDPOINT = "https://auth.yandex.cloud/oauth/revoke"
RESOURCE_MANAGER_ENDPOINT = "https://resource-manager.api.cloud.yandex.net/resource-manager/v1"
TOKEN_REFRESH_SKEW_SECONDS = 60
STATE_TTL_SECONDS = 600


class OAuthGatewayError(Exception):
    pass


class GatewayNotConnected(OAuthGatewayError):
    pass


class GatewayReauthorizationRequired(OAuthGatewayError):
    pass


class GatewayInvalidState(OAuthGatewayError):
    pass


class GatewayRemoteError(OAuthGatewayError):
    pass


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int


@dataclass(frozen=True)
class OAuthFolder:
    id: str
    name: str
    cloud_id: str
    cloud_name: str


@dataclass(frozen=True)
class PendingAuthorization:
    subject_id: str
    code_verifier: str
    expires_at: int


@dataclass(frozen=True)
class CachedIAMToken:
    access_token: str
    expires_at: int


class OAuthRemoteClient(Protocol):
    def exchange_code(self, code: str, code_verifier: str) -> OAuthTokens: ...

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens: ...

    def list_folders(self, access_token: str) -> tuple[OAuthFolder, ...]: ...

    def revoke(self, refresh_token: str) -> None: ...


class AuthorizationSessionRegistry:
    """Ephemeral ownership of OAuth state and PKCE verifiers."""

    def __init__(self):
        self._sessions: dict[str, PendingAuthorization] = {}

    def create(self, subject_id: str) -> tuple[str, str]:
        self._delete_expired()
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        self._sessions[state] = PendingAuthorization(
            subject_id=subject_id,
            code_verifier=code_verifier,
            expires_at=int(time.time()) + STATE_TTL_SECONDS,
        )
        return state, code_verifier

    def consume(self, state: str) -> PendingAuthorization:
        pending = self._sessions.pop(state, None)
        if pending is None or pending.expires_at < int(time.time()):
            raise GatewayInvalidState("OAuth link is unknown, expired, or already used")
        return pending

    def _delete_expired(self) -> None:
        now = int(time.time())
        for state, pending in tuple(self._sessions.items()):
            if pending.expires_at < now:
                del self._sessions[state]


class IAMTokenCache:
    """Ephemeral cache; long-lived credentials never enter this component."""

    def __init__(self):
        self._tokens: dict[str, CachedIAMToken] = {}

    def save(self, subject_id: str, tokens: OAuthTokens) -> None:
        self._tokens[subject_id] = CachedIAMToken(
            access_token=tokens.access_token,
            expires_at=int(time.time()) + tokens.expires_in,
        )

    def get(self, subject_id: str) -> str | None:
        cached = self._tokens.get(subject_id)
        if cached is None or cached.expires_at <= int(time.time()) + TOKEN_REFRESH_SKEW_SECONDS:
            return None
        return cached.access_token

    def delete(self, subject_id: str) -> None:
        self._tokens.pop(subject_id, None)


class YandexCloudOAuthClient:
    def __init__(self, config: OAuthGatewayConfig):
        self._config = config

    def exchange_code(self, code: str, code_verifier: str) -> OAuthTokens:
        return self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._config.redirect_uri,
                "code_verifier": code_verifier,
            }
        )

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        return self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    def revoke(self, refresh_token: str) -> None:
        self._request_json(
            REVOCATION_ENDPOINT,
            data={"token": refresh_token},
            headers=self._basic_auth_headers(),
        )

    def list_folders(self, access_token: str) -> tuple[OAuthFolder, ...]:
        headers = {"Authorization": f"Bearer {access_token}"}
        clouds = self._list_paginated("clouds", headers=headers)
        folders: list[OAuthFolder] = []
        for cloud in clouds:
            cloud_id = _response_string(cloud, "id", "cloud")
            cloud_name = _response_string(cloud, "name", "cloud")
            for folder in self._list_paginated(
                "folders", headers=headers, cloudId=cloud_id
            ):
                if folder.get("status") == "ACTIVE":
                    folders.append(
                        OAuthFolder(
                            id=_response_string(folder, "id", "folder"),
                            name=_response_string(folder, "name", "folder"),
                            cloud_id=cloud_id,
                            cloud_name=cloud_name,
                        )
                    )
        return tuple(sorted(folders, key=lambda item: (item.cloud_name, item.name)))

    def _token_request(self, data: dict[str, str]) -> OAuthTokens:
        response = self._request_json(
            TOKEN_ENDPOINT,
            data=data,
            headers=self._basic_auth_headers(),
        )
        access_token = response.get("access_token")
        expires_in = response.get("expires_in")
        if not isinstance(access_token, str) or not isinstance(expires_in, int):
            raise GatewayRemoteError("Yandex Cloud returned an invalid token response")
        refresh_token = response.get("refresh_token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise GatewayRemoteError("Yandex Cloud returned an invalid refresh token")
        return OAuthTokens(access_token, refresh_token, expires_in)

    def _list_paginated(
        self, resource: str, *, headers: dict[str, str], **query: str
    ) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        page_token: str | None = None
        while True:
            page_query = {"pageSize": "1000", **query}
            if page_token:
                page_query["pageToken"] = page_token
            response = self._request_json(
                f"{RESOURCE_MANAGER_ENDPOINT}/{resource}?{urlencode(page_query)}",
                headers=headers,
            )
            collection = response.get(resource)
            if not isinstance(collection, list):
                raise GatewayRemoteError(f"Yandex Cloud returned invalid {resource} data")
            for item in collection:
                if not isinstance(item, dict):
                    raise GatewayRemoteError(
                        f"Yandex Cloud returned an invalid {resource} item"
                    )
                items.append(cast(dict[str, object], item))
            next_page_token = response.get("nextPageToken")
            if not isinstance(next_page_token, str) or not next_page_token:
                return items
            page_token = next_page_token

    def _basic_auth_headers(self) -> dict[str, str]:
        raw = f"{self._config.client_id}:{self._config.client_secret}".encode("utf-8")
        return {
            "Authorization": "Basic " + base64.b64encode(raw).decode("ascii"),
            "Content-Type": "application/x-www-form-urlencoded",
        }

    @staticmethod
    def _request_json(
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        request = Request(
            url,
            data=urlencode(data).encode("utf-8") if data is not None else None,
            headers=headers or {},
            method="POST" if data is not None else "GET",
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            logger.warning("Yandex Cloud OAuth API returned HTTP %s", exc.code)
            raise GatewayRemoteError(f"Yandex Cloud API returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise GatewayRemoteError("Could not reach Yandex Cloud API") from exc
        if not payload.strip():
            return {}
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise GatewayRemoteError("Yandex Cloud API returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise GatewayRemoteError("Yandex Cloud API returned an invalid response")
        return parsed


class OAuthGateway:
    def __init__(
        self,
        config: OAuthGatewayConfig,
        credentials: EncryptedCredentialStore,
        remote: OAuthRemoteClient,
        sessions: AuthorizationSessionRegistry | None = None,
        iam_cache: IAMTokenCache | None = None,
    ):
        self._config = config
        self._credentials = credentials
        self._remote = remote
        self._sessions = sessions or AuthorizationSessionRegistry()
        self._iam_cache = iam_cache or IAMTokenCache()

    def begin_authorization(self, subject_id: str) -> str:
        state, code_verifier = self._sessions.create(subject_id)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._config.client_id,
                "redirect_uri": self._config.redirect_uri,
                "scope": " ".join(self._config.scopes),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{AUTHORIZATION_ENDPOINT}?{query}"

    def complete_authorization(self, code: str, state: str) -> str:
        pending = self._sessions.consume(state)
        tokens = self._remote.exchange_code(code, pending.code_verifier)
        if tokens.refresh_token is None:
            raise GatewayReauthorizationRequired(
                "Yandex Cloud did not return a refresh token"
            )
        self._credentials.save_refresh_token(pending.subject_id, tokens.refresh_token)
        self._iam_cache.save(pending.subject_id, tokens)
        return pending.subject_id

    def is_connected(self, subject_id: str) -> bool:
        return self._credentials.has_refresh_token(subject_id)

    def get_iam_token(self, subject_id: str) -> str:
        if not self._credentials.has_refresh_token(subject_id):
            raise GatewayNotConnected("Yandex Cloud is not connected")
        cached = self._iam_cache.get(subject_id)
        if cached is not None:
            return cached
        try:
            refresh_token = self._credentials.get_refresh_token(subject_id)
        except CredentialStoreError as exc:
            raise GatewayReauthorizationRequired(
                "Stored credentials cannot be read"
            ) from exc
        if refresh_token is None:
            raise GatewayNotConnected("Yandex Cloud is not connected")
        try:
            tokens = self._remote.refresh_access_token(refresh_token)
        except GatewayRemoteError as exc:
            raise GatewayReauthorizationRequired(
                "Yandex Cloud credentials expired or were revoked"
            ) from exc
        if tokens.refresh_token is not None:
            self._credentials.save_refresh_token(subject_id, tokens.refresh_token)
        self._iam_cache.save(subject_id, tokens)
        return tokens.access_token

    def list_folders(self, subject_id: str) -> tuple[OAuthFolder, ...]:
        return self._remote.list_folders(self.get_iam_token(subject_id))

    def validate_folder(self, subject_id: str, folder_id: str) -> None:
        if folder_id not in {folder.id for folder in self.list_folders(subject_id)}:
            raise GatewayRemoteError("The selected folder is not available to this user")

    def disconnect(self, subject_id: str) -> None:
        try:
            refresh_token = self._credentials.get_refresh_token(subject_id)
        except CredentialStoreError:
            refresh_token = None
        if refresh_token is not None:
            try:
                self._remote.revoke(refresh_token)
            except GatewayRemoteError:
                logger.warning("Could not revoke Yandex Cloud token for subject_id=%s", subject_id)
        self._iam_cache.delete(subject_id)
        self._credentials.delete_refresh_token(subject_id)


def _response_string(
    payload: dict[str, object], field: str, resource: str
) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise GatewayRemoteError(f"Yandex Cloud returned an invalid {resource} {field}")
    return value

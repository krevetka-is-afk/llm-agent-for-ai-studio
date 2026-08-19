from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

from aiohttp import ClientSession

from ai_studio_agent_builder.application.dto import UserCredentials

from .config import OAuthGatewayClientConfig


class OAuthGatewayClientError(Exception):
    pass


class GatewayClientNotConnected(OAuthGatewayClientError):
    pass


class GatewayClientReauthorizationRequired(OAuthGatewayClientError):
    pass


class GatewayClientUnavailable(OAuthGatewayClientError):
    pass


@dataclass(frozen=True)
class GatewayFolder:
    id: str
    name: str
    cloud_id: str
    cloud_name: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.cloud_name})"


class OAuthGatewayClient:
    def __init__(self, config: OAuthGatewayClientConfig):
        self._base_url = config.base_url
        self._headers = {"X-OAuth-Gateway-Key": config.shared_secret}

    async def begin_authorization(self, subject_id: str) -> str:
        payload = await self._request_json(
            "POST", f"/v1/users/{_path_subject(subject_id)}/authorization"
        )
        return _required_string(payload, "authorizationUrl")

    async def status(self, subject_id: str) -> bool:
        payload = await self._request_json(
            "GET", f"/v1/users/{_path_subject(subject_id)}/status"
        )
        connected = payload.get("connected")
        if not isinstance(connected, bool):
            raise GatewayClientUnavailable("OAuth Gateway returned invalid status")
        return connected

    async def list_folders(self, subject_id: str) -> tuple[GatewayFolder, ...]:
        payload = await self._request_json(
            "GET", f"/v1/users/{_path_subject(subject_id)}/folders"
        )
        raw_folders = payload.get("folders")
        if not isinstance(raw_folders, list):
            raise GatewayClientUnavailable("OAuth Gateway returned invalid folders")
        folders: list[GatewayFolder] = []
        for raw_folder in raw_folders:
            if not isinstance(raw_folder, dict):
                raise GatewayClientUnavailable("OAuth Gateway returned invalid folder")
            folder = cast(dict[str, object], raw_folder)
            folders.append(
                GatewayFolder(
                    id=_required_string(folder, "id"),
                    name=_required_string(folder, "name"),
                    cloud_id=_required_string(folder, "cloudId"),
                    cloud_name=_required_string(folder, "cloudName"),
                )
            )
        return tuple(folders)

    async def get_credentials(self, subject_id: str, folder_id: str) -> UserCredentials:
        payload = await self._request_json(
            "POST", f"/v1/users/{_path_subject(subject_id)}/credentials"
        )
        return UserCredentials(
            access_token=_required_string(payload, "accessToken"),
            folder_id=folder_id,
        )

    async def validate_folder(self, subject_id: str, folder_id: str) -> None:
        await self._request_json(
            "POST",
            f"/v1/users/{_path_subject(subject_id)}/folders/{_path_subject(folder_id)}/validate",
        )

    async def disconnect(self, subject_id: str) -> None:
        await self._request_json("DELETE", f"/v1/users/{_path_subject(subject_id)}")

    async def _request_json(self, method: str, path: str) -> dict[str, object]:
        try:
            async with ClientSession(headers=self._headers) as session:
                async with session.request(
                    method, f"{self._base_url}{path}"
                ) as response:
                    if response.status == 404:
                        raise GatewayClientNotConnected("Yandex Cloud is not connected")
                    if response.status == 401:
                        raise GatewayClientReauthorizationRequired(
                            "Yandex Cloud connection must be renewed"
                        )
                    if response.status >= 400:
                        raise GatewayClientUnavailable(
                            f"OAuth Gateway returned HTTP {response.status}"
                        )
                    if response.status == 204:
                        return {}
                    payload = await response.json(content_type=None)
        except (GatewayClientNotConnected, GatewayClientReauthorizationRequired):
            raise
        except Exception as exc:
            raise GatewayClientUnavailable("OAuth Gateway is unavailable") from exc
        if not isinstance(payload, dict):
            raise GatewayClientUnavailable("OAuth Gateway returned invalid JSON")
        return payload


def _path_subject(subject_id: str) -> str:
    return quote(subject_id, safe="")


def _required_string(payload: dict[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise GatewayClientUnavailable(f"OAuth Gateway returned invalid {name}")
    return value

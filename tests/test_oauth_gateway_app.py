import asyncio
from typing import cast

from aiohttp.test_utils import TestClient, TestServer

from experimental.oauth.app import create_gateway_app
from experimental.oauth.gateway import OAuthFolder, OAuthGateway


class StubGateway:
    def begin_authorization(self, subject_id: str) -> str:
        return f"https://auth.example/?subject={subject_id}"

    def is_connected(self, subject_id: str) -> bool:
        return True

    def list_folders(self, subject_id: str) -> tuple[OAuthFolder, ...]:
        return (
            OAuthFolder(
                id="folder-a",
                name="development",
                cloud_id="cloud-a",
                cloud_name="team-cloud",
            ),
        )

    def validate_folder(self, subject_id: str, folder_id: str) -> None:
        assert folder_id == "folder-a"

    def get_iam_token(self, subject_id: str) -> str:
        return "short-lived-iam-token"

    def disconnect(self, subject_id: str) -> None:
        return None


def test_gateway_api_requires_internal_secret_and_exposes_only_gateway_contract() -> None:
    async def scenario() -> None:
        app = create_gateway_app(cast(OAuthGateway, StubGateway()), "internal-secret")
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            unauthorized = await client.post("/v1/users/42/authorization")
            assert unauthorized.status == 401

            headers = {"X-OAuth-Gateway-Key": "internal-secret"}
            authorize = await client.post("/v1/users/42/authorization", headers=headers)
            assert await authorize.json() == {"authorizationUrl": "https://auth.example/?subject=42"}

            folders = await client.get("/v1/users/42/folders", headers=headers)
            assert (await folders.json())["folders"][0]["id"] == "folder-a"

            credentials = await client.post("/v1/users/42/credentials", headers=headers)
            assert (await credentials.json())["accessToken"] == "short-lived-iam-token"

            health = await client.get("/healthz")
            assert health.status == 200
            assert await health.json() == {"status": "ok"}
        finally:
            await client.close()

    asyncio.run(scenario())

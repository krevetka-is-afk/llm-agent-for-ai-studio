import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.miniapp_server import BOT_KEY, CONNECTOR_KEY, connect_api_handler
from src.yc_connect import (
    ConnectionStateStore,
    ConnectionStateUserMismatch,
    UsedConnectionState,
    YandexCloudConnector,
    mask_api_key,
    mask_folder_id,
)


class FakeUserStore:
    def __init__(self):
        self.api_tokens = {}
        self.folder_ids = {}

    def set_api_token(self, user_id: str, api_token: str) -> None:
        self.api_tokens[user_id] = api_token

    def set_folder_id(self, user_id: str, folder_id: str) -> None:
        self.folder_ids[user_id] = folder_id


class FakeVerifier:
    def __init__(self):
        self.calls = []

    async def verify(
        self,
        *,
        api_token: str,
        folder_id: str,
        base_url: str,
        timeout: float,
    ) -> None:
        self.calls.append(
            {
                "api_token": api_token,
                "folder_id": folder_id,
                "base_url": base_url,
                "timeout": timeout,
            }
        )


class FakeBot:
    token = "123:bot-token"


class FakeConnector:
    def __init__(self):
        self.calls = []

    async def connect(
        self,
        *,
        telegram_user_id: str,
        state: str,
        folder_id: str,
        api_token: str,
    ):
        self.calls.append(
            {
                "telegram_user_id": telegram_user_id,
                "state": state,
                "folder_id": folder_id,
                "api_token": api_token,
            }
        )
        return SimpleNamespace(
            folder_id_masked="b1g***789",
            api_key_masked="****3456",
        )


def test_masks_yandex_cloud_values() -> None:
    assert mask_api_key("abcdef123456") == "****123456"
    assert mask_api_key("abc") == "****"
    assert mask_folder_id("b1g123456789") == "b1g******789"
    assert mask_folder_id("b1g") == "b1***"


def test_state_store_rejects_user_mismatch() -> None:
    store = ConnectionStateStore(ttl_seconds=900)
    pending = store.create("user-1")

    with pytest.raises(ConnectionStateUserMismatch):
        store.validate(pending.state, "user-2")


def test_connector_verifies_saves_and_consumes_state() -> None:
    asyncio.run(_assert_connector_verifies_saves_and_consumes_state())


async def _assert_connector_verifies_saves_and_consumes_state() -> None:
    state_store = ConnectionStateStore(ttl_seconds=900)
    user_store = FakeUserStore()
    verifier = FakeVerifier()
    connector = YandexCloudConnector(
        state_store=state_store,
        user_store=user_store,
        verifier=verifier,
        base_url="https://ai.api.cloud.yandex.net/v1",
        verify_timeout=3.0,
    )
    pending = state_store.create("123")

    result = await connector.connect(
        telegram_user_id="123",
        state=pending.state,
        folder_id=" b1g123456789 ",
        api_token=" ApiKey123456 ",
    )

    assert result.folder_id_masked == "b1g******789"
    assert result.api_key_masked == "****123456"
    assert user_store.folder_ids == {"123": "b1g123456789"}
    assert user_store.api_tokens == {"123": "ApiKey123456"}
    assert verifier.calls == [
        {
            "api_token": "ApiKey123456",
            "folder_id": "b1g123456789",
            "base_url": "https://ai.api.cloud.yandex.net/v1",
            "timeout": 3.0,
        }
    ]

    with pytest.raises(UsedConnectionState):
        state_store.validate(pending.state, "123")


def test_connect_api_handler_validates_telegram_user_and_calls_connector() -> None:
    asyncio.run(_assert_connect_api_handler_validates_telegram_user_and_calls_connector())


async def _assert_connect_api_handler_validates_telegram_user_and_calls_connector() -> None:
    connector = FakeConnector()
    app = web.Application()
    app[BOT_KEY] = FakeBot()
    app[CONNECTOR_KEY] = connector
    app.router.add_post("/api/yc/connect", connect_api_handler)

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        with patch(
            "src.miniapp_server.safe_parse_webapp_init_data",
            return_value=SimpleNamespace(user=SimpleNamespace(id=123)),
        ):
            response = await client.post(
                "/api/yc/connect",
                json={
                    "state": "state-1",
                    "folder_id": "b1g123456789",
                    "api_key": "ApiKey123456",
                    "telegram_init_data": "raw-init-data",
                },
            )
            body = await response.json()
    finally:
        await client.close()

    assert response.status == 200
    assert body == {
        "ok": True,
        "folder_id_masked": "b1g***789",
        "api_key_masked": "****3456",
    }
    assert connector.calls == [
        {
            "telegram_user_id": "123",
            "state": "state-1",
            "folder_id": "b1g123456789",
            "api_token": "ApiKey123456",
        }
    ]

from config import ConnectionConfig
from context import AIStudioCredentials, get_api_key_client


def test_api_key_client_uses_yandex_api_key_authorization_scheme() -> None:
    client = get_api_key_client(
        AIStudioCredentials(
            api_key="AQAAAA-secret-api-key",
            folder_id="b1gfolder",
        ),
        ConnectionConfig(base_url="https://example.test/v1", timeout=10),
    )

    assert client.default_headers["Authorization"] == "Api-Key AQAAAA-secret-api-key"

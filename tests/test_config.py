from pathlib import Path

from cryptography.fernet import Fernet

from config import load_config, load_web_ui_config
from experimental.oauth.config import load_oauth_gateway_config


def test_oauth_is_optional_and_shared_yandex_credentials_are_not_required(
    monkeypatch,
) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:token")
    for name in (
        "YANDEX_API_KEY",
        "YANDEX_FOLDER_ID",
        "YC_OAUTH_CLIENT_ID",
        "YC_OAUTH_CLIENT_SECRET",
        "YC_OAUTH_REDIRECT_URI",
        "YC_TOKEN_ENCRYPTION_KEY",
        "YC_API_KEY_ENCRYPTION_KEY",
        "OAUTH_GATEWAY_URL",
        "OAUTH_GATEWAY_SHARED_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    load_config(Path("config.yaml"))

def test_gateway_reads_yandex_cloud_secrets_without_loading_bot_config(monkeypatch) -> None:
    monkeypatch.setenv("YC_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("YC_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("YC_OAUTH_REDIRECT_URI", "https://gateway.example/yc/oauth/callback")
    monkeypatch.setenv("YC_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("OAUTH_GATEWAY_SHARED_SECRET", "shared-secret")

    config = load_oauth_gateway_config()

    assert config.client_id == "client-id"
    assert config.shared_secret == "shared-secret"


def test_bot_reads_optional_http_proxy_url(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:token")
    monkeypatch.setenv("TELEGRAM_PROXY_URL", "https://user:password@proxy.example:8443")

    config = load_config(Path("config.yaml"))

    assert config.bot.telegram_proxy_url == "https://user:password@proxy.example:8443"


def test_web_ui_uses_gateway_without_requiring_telegram_token(monkeypatch) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("YC_API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    config = load_web_ui_config(Path("config.yaml"))

    assert config.api_key_store.storage_path.name == "yc_api_keys.db"
    assert config.ai_service.consultant.model_name

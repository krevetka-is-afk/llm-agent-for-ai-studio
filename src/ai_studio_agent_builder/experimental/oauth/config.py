import os

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OAuthGatewayClientConfig:
    base_url: str
    shared_secret: str


@dataclass(frozen=True)
class OAuthGatewayConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    encryption_key: str
    storage_path: Path
    callback_host: str
    callback_port: int
    scopes: tuple[str, ...]
    shared_secret: str


def load_oauth_gateway_config() -> OAuthGatewayConfig:
    required_names = (
        "YC_OAUTH_CLIENT_ID",
        "YC_OAUTH_CLIENT_SECRET",
        "YC_OAUTH_REDIRECT_URI",
        "YC_TOKEN_ENCRYPTION_KEY",
        "OAUTH_GATEWAY_SHARED_SECRET",
    )
    values = {name: os.getenv(name) for name in required_names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Incomplete OAuth Gateway configuration; missing: " + ", ".join(missing)
        )

    scopes = tuple(
        scope
        for scope in os.getenv("YC_OAUTH_SCOPES", "openid profile email").split()
        if scope
    )
    return OAuthGatewayConfig(
        client_id=_required_value(values, "YC_OAUTH_CLIENT_ID"),
        client_secret=_required_value(values, "YC_OAUTH_CLIENT_SECRET"),
        redirect_uri=_required_value(values, "YC_OAUTH_REDIRECT_URI"),
        encryption_key=_required_value(values, "YC_TOKEN_ENCRYPTION_KEY"),
        storage_path=Path(os.getenv("YC_OAUTH_DB_PATH", "yc_oauth.db")).resolve(),
        callback_host=os.getenv("YC_OAUTH_CALLBACK_HOST", "0.0.0.0"),
        callback_port=int(os.getenv("YC_OAUTH_CALLBACK_PORT", "8080")),
        scopes=scopes,
        shared_secret=_required_value(values, "OAUTH_GATEWAY_SHARED_SECRET"),
    )


def load_oauth_gateway_client_config() -> OAuthGatewayClientConfig | None:
    required_names = ("OAUTH_GATEWAY_URL", "OAUTH_GATEWAY_SHARED_SECRET")
    values = {name: os.getenv(name) for name in required_names}
    if all(value is None for value in values.values()):
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Incomplete OAuth Gateway client configuration; missing: "
            + ", ".join(missing)
        )
    return OAuthGatewayClientConfig(
        base_url=_required_value(values, "OAUTH_GATEWAY_URL").rstrip("/"),
        shared_secret=_required_value(values, "OAUTH_GATEWAY_SHARED_SECRET"),
    )


def _required_value(values: dict[str, str | None], name: str) -> str:
    value = values[name]
    if not value:
        raise RuntimeError(f"Missing required OAuth environment variable: {name}")
    return value

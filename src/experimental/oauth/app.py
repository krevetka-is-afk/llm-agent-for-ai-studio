import asyncio
import logging
from html import escape

from aiohttp import web

from logging_config import configure_console_logging

from .config import load_oauth_gateway_config
from .credential_store import EncryptedCredentialStore
from .gateway import (
    GatewayInvalidState,
    GatewayNotConnected,
    GatewayReauthorizationRequired,
    GatewayRemoteError,
    OAuthGateway,
    OAuthGatewayError,
    YandexCloudOAuthClient,
)

logger = logging.getLogger(__name__)
OAUTH_GATEWAY_KEY: web.AppKey[OAuthGateway] = web.AppKey("oauth_gateway", OAuthGateway)


def create_gateway_app(gateway: OAuthGateway, shared_secret: str) -> web.Application:
    @web.middleware
    async def internal_api_auth(request: web.Request, handler):
        if (
            request.path.startswith("/v1/")
            and request.headers.get("X-OAuth-Gateway-Key") != shared_secret
        ):
            raise web.HTTPUnauthorized(text="Invalid OAuth Gateway credentials")
        return await handler(request)

    app = web.Application(middlewares=[internal_api_auth])
    app.router.add_post("/v1/users/{subject_id}/authorization", _begin_authorization)
    app.router.add_get("/v1/users/{subject_id}/status", _status)
    app.router.add_get("/v1/users/{subject_id}/folders", _folders)
    app.router.add_post(
        "/v1/users/{subject_id}/folders/{folder_id}/validate", _validate_folder
    )
    app.router.add_post("/v1/users/{subject_id}/credentials", _credentials)
    app.router.add_delete("/v1/users/{subject_id}", _disconnect)
    app.router.add_get("/yc/oauth/callback", _callback)
    app.router.add_get("/healthz", _health)
    app[OAUTH_GATEWAY_KEY] = gateway
    return app


async def _begin_authorization(request: web.Request) -> web.Response:
    gateway = _gateway(request)
    authorization_url = await asyncio.to_thread(
        gateway.begin_authorization, request.match_info["subject_id"]
    )
    return web.json_response({"authorizationUrl": authorization_url})


async def _status(request: web.Request) -> web.Response:
    connected = await asyncio.to_thread(
        _gateway(request).is_connected, request.match_info["subject_id"]
    )
    return web.json_response({"connected": connected})


async def _folders(request: web.Request) -> web.Response:
    try:
        folders = await asyncio.to_thread(
            _gateway(request).list_folders, request.match_info["subject_id"]
        )
    except OAuthGatewayError as exc:
        raise _gateway_http_error(exc) from exc
    return web.json_response(
        {
            "folders": [
                {
                    "id": folder.id,
                    "name": folder.name,
                    "cloudId": folder.cloud_id,
                    "cloudName": folder.cloud_name,
                }
                for folder in folders
            ]
        }
    )


async def _credentials(request: web.Request) -> web.Response:
    try:
        access_token = await asyncio.to_thread(
            _gateway(request).get_iam_token, request.match_info["subject_id"]
        )
    except OAuthGatewayError as exc:
        raise _gateway_http_error(exc) from exc
    return web.json_response({"accessToken": access_token})


async def _validate_folder(request: web.Request) -> web.Response:
    try:
        await asyncio.to_thread(
            _gateway(request).validate_folder,
            request.match_info["subject_id"],
            request.match_info["folder_id"],
        )
    except OAuthGatewayError as exc:
        raise _gateway_http_error(exc) from exc
    return web.Response(status=204)


async def _disconnect(request: web.Request) -> web.Response:
    await asyncio.to_thread(
        _gateway(request).disconnect, request.match_info["subject_id"]
    )
    return web.Response(status=204)


async def _callback(request: web.Request) -> web.Response:
    if request.query.get("error"):
        return _html_response(400, "Подключение Yandex Cloud отменено или отклонено.")
    code = request.query.get("code")
    state = request.query.get("state")
    if not code or not state:
        return _html_response(400, "Некорректный OAuth callback.")
    try:
        await asyncio.to_thread(_gateway(request).complete_authorization, code, state)
    except OAuthGatewayError:
        logger.exception("Yandex Cloud OAuth callback failed")
        return _html_response(
            400,
            "Не удалось завершить подключение. Вернитесь в приложение и начните подключение заново.",
        )
    return _html_response(
        200,
        "Yandex Cloud подключен. Вернитесь в открытую вкладку приложения.",
    )


async def _health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def _gateway(request: web.Request) -> OAuthGateway:
    return request.app[OAUTH_GATEWAY_KEY]


def _gateway_http_error(exc: OAuthGatewayError) -> web.HTTPException:
    if isinstance(exc, GatewayNotConnected):
        return web.HTTPNotFound(text="Yandex Cloud is not connected")
    if isinstance(exc, GatewayReauthorizationRequired):
        return web.HTTPUnauthorized(text="Yandex Cloud connection must be renewed")
    if isinstance(exc, GatewayRemoteError):
        return web.HTTPBadGateway(text="Yandex Cloud is unavailable")
    if isinstance(exc, GatewayInvalidState):
        return web.HTTPBadRequest(text="Invalid OAuth state")
    return web.HTTPInternalServerError(text="OAuth Gateway error")


def _html_response(status: int, message: str) -> web.Response:
    body = (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        "<title>Yandex Cloud</title></head><body><p>"
        f"{escape(message)}"
        "</p></body></html>"
    )
    return web.Response(status=status, text=body, content_type="text/html")


def main() -> None:
    configure_console_logging()
    config = load_oauth_gateway_config()
    gateway = OAuthGateway(
        config,
        EncryptedCredentialStore(config.storage_path, config.encryption_key),
        YandexCloudOAuthClient(config),
    )
    web.run_app(
        create_gateway_app(gateway, config.shared_secret),
        host=config.callback_host,
        port=config.callback_port,
    )


if __name__ == "__main__":
    main()

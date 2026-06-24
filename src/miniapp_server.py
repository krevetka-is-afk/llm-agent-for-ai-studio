import logging
from typing import Any

from aiohttp import web
from aiogram import Bot
from aiogram.utils.web_app import safe_parse_webapp_init_data

from config import AppConfig
from context import UserSecretsStore
from yc_connect import (
    ConnectionStateError,
    ConnectionStateStore,
    InvalidYandexCloudCredentials,
    OpenAIYandexCloudCredentialsVerifier,
    YandexCloudConnector,
)

logger = logging.getLogger(__name__)

BOT_KEY: web.AppKey[Any] = web.AppKey("bot", object)
CONNECTOR_KEY: web.AppKey[Any] = web.AppKey(
    "connector",
    object,
)


def create_miniapp_web_app(
    *,
    bot: Bot,
    config: AppConfig,
    user_store: UserSecretsStore,
    state_store: ConnectionStateStore,
) -> web.Application:
    app = web.Application()
    connector = YandexCloudConnector(
        state_store=state_store,
        user_store=user_store,
        verifier=OpenAIYandexCloudCredentialsVerifier(),
        base_url=config.connection.base_url,
        verify_timeout=config.mini_app.verify_timeout,
    )

    app[BOT_KEY] = bot
    app[CONNECTOR_KEY] = connector
    app.router.add_get("/yc/connect", connect_page_handler)
    app.router.add_post("/api/yc/connect", connect_api_handler)
    return app


async def start_miniapp_server(
    app: web.Application,
    *,
    host: str,
    port: int,
) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logger.info("Mini App server started on %s:%s", host, port)
    return runner


async def connect_page_handler(request: web.Request) -> web.Response:
    state = request.query.get("state", "")
    return web.Response(
        text=_render_connect_page(state),
        content_type="text/html",
        charset="utf-8",
    )


async def connect_api_handler(request: web.Request) -> web.Response:
    bot = request.app[BOT_KEY]
    connector = request.app[CONNECTOR_KEY]

    try:
        payload = await request.json()
    except ValueError:
        return _json_error("Invalid JSON body", status=400)

    state = str(payload.get("state", ""))
    folder_id = str(payload.get("folder_id", ""))
    api_token = str(payload.get("api_key", ""))
    init_data = str(payload.get("telegram_init_data", ""))

    try:
        webapp_data = safe_parse_webapp_init_data(
            token=bot.token,
            init_data=init_data,
        )
    except ValueError:
        return _json_error("Invalid Telegram WebApp auth data", status=401)

    if webapp_data.user is None:
        return _json_error("Telegram WebApp user is missing", status=401)

    telegram_user_id = str(webapp_data.user.id)

    try:
        result = await connector.connect(
            telegram_user_id=telegram_user_id,
            state=state,
            folder_id=folder_id,
            api_token=api_token,
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except ConnectionStateError as exc:
        return _json_error(str(exc), status=409)
    except InvalidYandexCloudCredentials:
        return _json_error("Yandex Cloud credentials check failed", status=400)

    return web.json_response(
        {
            "ok": True,
            "folder_id_masked": result.folder_id_masked,
            "api_key_masked": result.api_key_masked,
        }
    )


def _json_error(message: str, *, status: int) -> web.Response:
    return web.json_response({"ok": False, "detail": message}, status=status)


def _render_connect_page(state: str) -> str:
    escaped_state = (
        state.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Yandex Cloud</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: var(--tg-theme-bg-color, #f6f7f9);
      --text: var(--tg-theme-text-color, #18202a);
      --hint: var(--tg-theme-hint-color, #6b7280);
      --button: var(--tg-theme-button-color, #2563eb);
      --button-text: var(--tg-theme-button-text-color, #ffffff);
      --field: var(--tg-theme-secondary-bg-color, #ffffff);
      --border: rgba(120, 130, 150, 0.35);
      --danger: #b42318;
      --ok: #16794c;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    main {{
      width: min(100%, 520px);
      margin: 0 auto;
      padding: 28px 18px 24px;
    }}

    h1 {{
      margin: 0 0 10px;
      font-size: 24px;
      line-height: 1.2;
      font-weight: 700;
    }}

    p {{
      margin: 0 0 22px;
      color: var(--hint);
      font-size: 15px;
      line-height: 1.45;
    }}

    label {{
      display: block;
      margin: 18px 0 8px;
      font-size: 14px;
      font-weight: 650;
    }}

    input {{
      width: 100%;
      height: 48px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--field);
      color: var(--text);
      padding: 0 13px;
      font-size: 16px;
      outline: none;
    }}

    input:focus {{
      border-color: var(--button);
    }}

    button {{
      width: 100%;
      height: 48px;
      margin-top: 24px;
      border: 0;
      border-radius: 8px;
      background: var(--button);
      color: var(--button-text);
      font-size: 16px;
      font-weight: 700;
    }}

    button:disabled {{
      opacity: 0.62;
    }}

    .message {{
      min-height: 22px;
      margin-top: 14px;
      font-size: 14px;
      line-height: 1.35;
    }}

    .error {{
      color: var(--danger);
    }}

    .success {{
      color: var(--ok);
    }}
  </style>
</head>
<body>
  <main>
    <h1>Подключение Yandex Cloud</h1>
    <p>Введите folder id и API key. Ключ будет отправлен на backend по HTTPS и не попадёт в сообщение Telegram.</p>

    <input id="state" type="hidden" value="{escaped_state}">

    <label for="folder_id">Folder ID</label>
    <input id="folder_id" name="folder_id" autocomplete="off" inputmode="text">

    <label for="api_key">API key</label>
    <input id="api_key" name="api_key" type="password" autocomplete="off">

    <button id="submit" type="button">Проверить и сохранить</button>
    <div id="message" class="message"></div>
  </main>

  <script>
    const tg = window.Telegram && window.Telegram.WebApp;
    const submitBtn = document.getElementById("submit");
    const messageEl = document.getElementById("message");

    if (tg) {{
      tg.ready();
      tg.expand();
    }}

    function setMessage(text, kind) {{
      messageEl.textContent = text;
      messageEl.className = "message " + kind;
    }}

    async function submit() {{
      setMessage("", "");
      submitBtn.disabled = true;
      submitBtn.textContent = "Проверяем...";

      try {{
        const response = await fetch("/api/yc/connect", {{
          method: "POST",
          headers: {{"Content-Type": "application/json"}},
          body: JSON.stringify({{
            state: document.getElementById("state").value,
            folder_id: document.getElementById("folder_id").value.trim(),
            api_key: document.getElementById("api_key").value.trim(),
            telegram_init_data: tg ? tg.initData : ""
          }})
        }});

        const data = await response.json().catch(() => ({{}}));
        if (!response.ok || !data.ok) {{
          throw new Error(data.detail || "Не удалось подключить Yandex Cloud");
        }}

        setMessage("Yandex Cloud подключён. Можно закрыть окно.", "success");
        if (tg) {{
          tg.showPopup({{
            title: "Готово",
            message: "Yandex Cloud подключён.",
            buttons: [{{type: "ok"}}]
          }});
          setTimeout(() => tg.close(), 800);
        }}
      }} catch (err) {{
        setMessage(err.message, "error");
      }} finally {{
        submitBtn.disabled = false;
        submitBtn.textContent = "Проверить и сохранить";
      }}
    }}

    submitBtn.addEventListener("click", submit);
  </script>
</body>
</html>"""

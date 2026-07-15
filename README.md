# llm-agent-for-ai-studio
Ассистент, который поможет пользователям собирать агентов из кубиков AI studio.

## Установка

### Пререквизит

`uv` & `≥python3.14`

### Клонируем репозиторий

```bash
git clone https://github.com/krevetka-is-afk/llm-agent-for-ai-studio.git
cd llm-agent-for-ai-studio
```

### Устанавливаем зависимости

```bash
uv sync --frozen
```

#### Для участия в разработке необходимо дополнительно

```bash
uv run pre-commit install
```

##### Перед коммитом

```bash
uv run pre-commit run --all-files
```

## Запуск проекта

Основной способ запуска - web-интерфейс с API-ключами пользователей:

```bash
PYTHONPATH=src uv run --env-file .env.web streamlit run src/ui/app.py
```

### Экспериментальный OAuth Gateway

Замороженный прототип OAuth находится в `src/experimental/oauth/` и не входит в
обычный запуск. Он сохранён для будущей проверки сценария с Identity Hub.

OAuth работает как отдельный сервис `oauth-gateway`: Telegram-бот не получает
refresh-токены и не содержит OAuth client secret. Для авторизации через
`auth.yandex.cloud` нужны два объекта: IAM OAuth client с redirect URI
`https://<домен>/yc/oauth/callback` и связанное с ним OIDC-приложение Identity Hub
с назначенными пользователями. Полная процедура приведена в
[YANDEX_CLOUD_USER_OAUTH.md](YANDEX_CLOUD_USER_OAUTH.md).

Переменные Telegram-бота в `.env.bot`:

```dotenv
BOT_TOKEN=...
OAUTH_GATEWAY_URL=http://oauth-gateway:8080
OAUTH_GATEWAY_SHARED_SECRET=<long random value>
# Опционально: HTTP/HTTPS proxy для Bot API, например https://user:password@proxy.example:8443
TELEGRAM_PROXY_URL=...
```

Переменные Gateway в `.env.gateway`:

```dotenv
YC_OAUTH_CLIENT_ID=...
YC_OAUTH_CLIENT_SECRET=...
YC_OAUTH_REDIRECT_URI=https://<домен>/yc/oauth/callback
YC_OAUTH_SCOPES=openid profile email
YC_TOKEN_ENCRYPTION_KEY=<Fernet key>
YC_OAUTH_CALLBACK_HOST=0.0.0.0
YC_OAUTH_CALLBACK_PORT=8080
YC_OAUTH_DB_PATH=/data/refresh_tokens.db
OAUTH_GATEWAY_SHARED_SECRET=<same long random value>
```

Сгенерировать ключ шифрования можно так:

```bash
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

В production callback Gateway должен быть доступен по HTTPS через reverse proxy.
После подтверждения доступа пользователь возвращается в Telegram и выполняет
`/yc_folders`. Подробности и требования к OAuth client приведены в
[YANDEX_CLOUD_USER_OAUTH.md](YANDEX_CLOUD_USER_OAUTH.md).

Для отдельного запуска Gateway используйте:

```bash
PYTHONPATH=src uv run --env-file .env.gateway python -m experimental.oauth.app
```

Во втором терминале можно запустить экспериментального Telegram-бота:

```bash
PYTHONPATH=src uv run --env-file .env.bot python src/app.py
```

Для staging-сервера с Caddy используйте
[`deploy/Caddyfile.bot-staging`](deploy/Caddyfile.bot-staging): он публикует только
`/yc/oauth/callback`, а Docker Gateway остаётся привязанным к localhost. Скрипт
`deploy/start-telegram-bot.sh` запросит `BOT_TOKEN` без отображения и создаст
`.env.bot` с правами `0600`.

## Web-интерфейс для тестирования

`web-ui` запускает Streamlit на `agent-builder.s3rg.ru`. Пользователь создаёт
API-ключ сервисного аккаунта в интерфейсе AI Studio и один раз вводит его вместе с
ID каталога. Ключ отправляется только в Streamlit backend, проверяется минимальным
запросом к AI Studio и хранится зашифрованным в Docker volume. Для запуска нужен
`.env.web`:

```dotenv
YC_API_KEY_ENCRYPTION_KEY=<Fernet key>
YC_API_KEY_DB_PATH=/data/api_keys.db
```

Создать ключ можно в AI Studio: «Создать API-ключ». Он создаётся для сервисного
аккаунта с необходимыми ролями; укажите срок действия ключа. API-ключ никогда не
отправляется в чат и не выводится UI после сохранения.

### Что нужно пользователю

1. Открыть [Yandex AI Studio](https://aistudio.yandex.ru/), выбрать каталог и
   нажать «Создать API-ключ».
2. Скопировать секретную часть ключа до закрытия диалога.
3. Открыть [список каталогов в консоли](https://console.yandex.cloud/folders),
   выбрать тот же каталог и скопировать его ID под названием каталога.
4. Ввести оба значения в форму подключения на `agent-builder.s3rg.ru`.

Подробные официальные инструкции: [создание ключа](https://aistudio.yandex.ru/docs/ru/ai-studio/operations/get-api-key.html) и [получение ID каталога](https://yandex.cloud/ru/docs/resource-manager/operations/folder/get-id).

OAuth Gateway оставлен как эксперимент: он не запускается по умолчанию. Для
отдельного теста используйте `docker compose --profile oauth-experimental up -d`.

## Запуск в docker

```bash
docker build -t my-rag-agent .
docker compose up -d --build
```

Для эксперимента с OAuth используйте `docker compose --profile oauth-experimental`
и подготовьте `.env.gateway` из раздела выше. Перед публикацией callback настройте reverse proxy с HTTPS на
`http://oauth-gateway:8080/yc/oauth/callback` и используйте его публичный URL как
`YC_OAUTH_REDIRECT_URI`. Для web UI стандартный запуск не требует OAuth Gateway:
Docker volume `api-key-credentials` хранит только зашифрованные API-ключи.

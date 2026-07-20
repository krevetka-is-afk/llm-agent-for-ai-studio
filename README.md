# llm-agent-for-ai-studio
Ассистент, который поможет пользователям собирать агентов из кубиков AI studio.

## Установка

### Пререквизит

`uv` & Python `3.13`

### Клонируем репозиторий

```bash
git clone https://github.com/krevetka-is-afk/llm-agent-for-ai-studio.git
cd llm-agent-for-ai-studio
```

### Устанавливаем зависимости

```bash
uv sync --frozen
```

### Быстрый запуск Web UI

```bash
cp .env.web.example .env.web
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode("ascii"))'
```

Вставьте сгенерированный ключ в `YC_API_KEY_ENCRYPTION_KEY` внутри `.env.web`.
По умолчанию Docker хранит runtime-файлы в `/data`; локально можно оставить эти
пути или заменить их на относительные:

```dotenv
UPLOADED_FILES_DIR=uploaded_files
CONVERSATION_DB_PATH=conversation.db
YC_API_KEY_DB_PATH=yc_api_keys.db
```

Запуск:

```bash
PYTHONPATH=src uv run --env-file .env.web streamlit run src/ui/app.py
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

### Telegram: ручное подключение API-ключом

Текущий Telegram-бот не использует OAuth. В личном чате с ботом пользователь
последовательно отправляет:

```text
/set_api_token <API-ключ>
/set_folder_id <ID каталога>
```

После проверки минимальным запросом к AI Studio бот сохраняет подключение только
в памяти процесса и удаляет оба исходных сообщения с API-ключом и ID каталога.
При неуспешной проверке сообщения не удаляются, чтобы пользователь мог исправить
значение. Команды с секретами отклоняются в группах и каналах.

Переменные Telegram-бота в `.env.bot`:

```dotenv
BOT_TOKEN=...
# Опционально: HTTP/HTTPS proxy для Bot API, например https://user:password@proxy.example:8443
TELEGRAM_PROXY_URL=...
UPLOADED_FILES_DIR=/data/uploaded_files
CONVERSATION_DB_PATH=/data/conversation.db
```

Запуск бота:

```bash
PYTHONPATH=src uv run --env-file .env.bot python src/app.py
```

### Экспериментальный OAuth Gateway

Замороженный прототип OAuth находится в `src/experimental/oauth/` и не входит в
обычный запуск. Он сохранён для будущей проверки сценария с Identity Hub.

OAuth работает как отдельный сервис `oauth-gateway`: Telegram-бот не получает
refresh-токены и не содержит OAuth client secret. Для авторизации через
`auth.yandex.cloud` нужны два объекта: IAM OAuth client с redirect URI
`https://<домен>/yc/oauth/callback` и связанное с ним OIDC-приложение Identity Hub
с назначенными пользователями. Процедура настройки пока не входит в документацию
Web MVP.

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
Этот прототип пока не подключён к Telegram-боту и Streamlit.

Для отдельного запуска Gateway используйте:

```bash
PYTHONPATH=src uv run --env-file .env.gateway python -m experimental.oauth.app
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
UPLOADED_FILES_DIR=/data/uploaded_files
CONVERSATION_DB_PATH=/data/conversation.db
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

### Слой результата

`AIInteractionService` возвращает не только текст модели, но и типизированные
блоки результата. Для RAG слой связывает события вызова инструмента с его
фактическим ответом и формирует блок векторного индекса с именем, ID и файлами.
Streamlit рисует эти данные отдельной карточкой, а Telegram получает текстовую
проекцию тех же блоков. Markdown модели остаётся самостоятельной диалоговой
частью и не используется как источник технических идентификаторов.

OAuth Gateway оставлен как эксперимент: он не запускается по умолчанию. Для
отдельного теста используйте `docker compose --profile oauth-experimental up -d`.

### Credentialed E2E

Credentialed Yandex AI Studio E2E tests are opt-in and use a dedicated API key
and folder. The test uploads a tiny synthetic file, creates a one-day vector
store, verifies the structured result, and then attempts to delete the remote
resources. The call can consume quota; cleanup is best-effort. Copy
`.env.e2e.example` to `.env.e2e`, set `RUN_YANDEX_AI_STUDIO_E2E=1`,
`YC_AI_STUDIO_API_KEY`, and `YC_AI_STUDIO_FOLDER_ID`, then run:

```bash
PYTHONPATH=src uv run --env-file .env.e2e pytest -m yandex_ai_studio_e2e tests/e2e/test_yandex_ai_studio_rag_e2e.py
```

Use a dedicated short-lived key with the minimum role needed to manage AI Studio
files and vector stores (`ai.assistants.admin`). Normal test runs skip these
tests and do not call AI Studio. Set `YC_AI_STUDIO_E2E_KEEP_REMOTE=1` only while
debugging; remote files and the vector store will then remain billable until
they are deleted manually or expire.

## Запуск в docker

```bash
cp .env.web.example .env.web
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode("ascii"))'
# Вставьте ключ в YC_API_KEY_ENCRYPTION_KEY внутри .env.web.
docker compose up -d --build
```

Для эксперимента с OAuth используйте `docker compose --profile oauth-experimental`
и подготовьте `.env.gateway` из раздела выше. Перед публикацией callback настройте reverse proxy с HTTPS на
`http://oauth-gateway:8080/yc/oauth/callback` и используйте его публичный URL как
`YC_OAUTH_REDIRECT_URI`. Для web UI стандартный запуск не требует OAuth Gateway:
Docker volume `web-data` хранит зашифрованные API-ключи, базу диалогов и
загруженные файлы. Контейнер запускается от non-root пользователя и имеет
healthcheck на `/_stcore/health`.

Web UI принимает не более 5 файлов за запрос: до 10 МБ на файл и до 25 МБ
суммарно. Streamlit ограничивает размер каждого upload до буферизации, а Docker
ограничивает web-контейнер 1 ГБ памяти и 256 процессами. Локальные env-файлы с
секретами храните с правами `0600`, например `chmod 600 .env.web`.

## Зависимости

Web runtime: `streamlit`, `openai-agents`, `openai`, `cryptography`, `pyyaml`,
`aiofiles` и транзитивные пакеты, которые попадают в production lock.

Telegram/OAuth experimental: `aiogram`, `aiohttp` и `cryptography`; эти сервисы
запускаются через compose profiles `telegram-experimental` и
`oauth-experimental`.

Неиспользуемые прямые зависимости ChatKit, LangChain и dotenv удалены из
production dependency set; транзитивный `python-dotenv` остаётся зависимостью
`openai-agents`, а `ty` — только dev-инструментом.

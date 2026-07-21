# Web UI

## Настройка

Создайте `.env.web` из примера и задайте Fernet-ключ:

```bash
cp .env.web.example .env.web
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode("ascii"))'
```

Минимальные переменные:

```dotenv
YC_API_KEY_ENCRYPTION_KEY=<Fernet key>
YC_API_KEY_DB_PATH=.local/api_keys.db
UPLOADED_FILES_DIR=.local/uploaded_files
CONVERSATION_DB_PATH=.local/conversation.db
```

При локальном запуске базы и загруженные файлы сохраняются в доступном для
записи каталоге `.local/`, который исключён из Git. Docker Compose отдельно
переопределяет эти пути на `/data/...` внутри persistent volume.

## Пользовательский поток

1. Создать API-ключ сервисного аккаунта в
   [Yandex AI Studio](https://aistudio.yandex.ru/).
2. Скопировать ID выбранного каталога.
3. Ввести ключ и ID каталога в sidebar.
4. После проверки отправить запрос или приложить до пяти файлов.
5. Уточнить недостающие обязательные параметры, которые вернёт валидатор.
6. Подтвердить итоговый system prompt и скачать готовую
   `AgentSpecification` в JSON. Для RAG интерфейс отдельно показывает имя и ID
   созданного vector index.

Лимиты: до 10 МБ на файл и до 25 МБ на один запрос. PDF доступен для скачивания,
но не встраивается в небезопасный browser preview.

API-ключ отправляется только backend-компоненту подключения, хранится
зашифрованным и не включается в сообщения, result parts или tool context.

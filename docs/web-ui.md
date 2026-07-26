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
6. Подтвердить итоговый system prompt и дождаться карточки готовой
   `AgentSpecification`. Для RAG интерфейс отдельно показывает имя и ID
   созданного vector index.
7. Ввести «Тестовый запрос к агенту» и нажать «Протестировать агента».
8. Проверить ответ, источники, token usage и `response_id`. Preview сохраняется
   между Streamlit rerun и относится только к конкретной карточке спецификации.
9. Скачать исходный `agent-specification.json` и, в разделе «Расширенные
   настройки», исполняемый `responses-agent-config.json`.

Лимиты: до 10 МБ на файл и до 25 МБ на один запрос. PDF доступен для скачивания,
но не встраивается в небезопасный browser preview.

API-ключ отправляется только backend-компоненту подключения, хранится
зашифрованным и не включается в сообщения, result parts или tool context.
Тестовый запуск stateless: он не изменяет builder conversation state и не
создаёт постоянный `agent_id`. Для RAG используется временный vector store;
если его TTL истёк, интерфейс предложит пересоздать RAG-конфигурацию.

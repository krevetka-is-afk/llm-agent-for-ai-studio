# Telegram adapter (experimental)

Telegram-бот не использует OAuth и запускается только через профиль
`telegram-experimental`.

```bash
uv run --env-file .env.bot python -m ai_studio_agent_builder.entrypoints.telegram
```

Подключение выполняется в личном чате:

```text
/set_api_token <API-ключ>
/set_folder_id <ID каталога>
```

Pending credentials живут в памяти не более пяти минут. После успешной проверки
исходные сообщения удаляются. Команда `/clear_credentials` удаляет активные и
pending credentials, очищает историю сессии и повторно пытается удалить сообщения
с секретами.

Запросы одного пользователя сериализуются через per-user lock, а запросы разных
пользователей выполняются независимо. Состояние агента меняется только после
успешного ответа.

Переменные `.env.bot`:

```dotenv
BOT_TOKEN=...
TELEGRAM_PROXY_URL=...
UPLOADED_FILES_DIR=/data/uploaded_files
CONVERSATION_DB_PATH=/data/conversation.db
```

Хранилище credentials остаётся in-memory; Telegram adapter пока нельзя считать
production account system.

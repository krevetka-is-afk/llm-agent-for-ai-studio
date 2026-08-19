# Deployment

## Web MVP

```bash
cp .env.web.example .env.web
docker compose up -d --build
```

Web UI доступен на `127.0.0.1:8501`. Docker Compose переопределяет локальные
пути из `.env.web` на `/data/...`, поэтому runtime data хранится в volume
`web-data`. Контейнер запускается от non-root пользователя и имеет:

- healthcheck `/_stcore/health`;
- `mem_limit: 1g`;
- `pids_limit: 256`;
- init-процесс для корректной обработки сигналов;
- read-only root filesystem и отдельный ограниченный `/tmp`;
- сброшенные Linux capabilities;
- `no-new-privileges:true`.

## Experimental profiles

```bash
docker compose --profile telegram-experimental up -d --build telegram-bot
docker compose --profile oauth-experimental up -d --build oauth-gateway
```

Для OAuth callback нужен HTTPS reverse proxy на
`http://oauth-gateway:8080/yc/oauth/callback`. Локальные `.env.*` с секретами не
коммитятся; рекомендуется режим доступа `0600`.

Перед релизом проверьте Compose config, соберите image и выполните обычный quality
gate из [testing.md](testing.md).

## Smoke-проверка Web UI

```bash
docker compose config --quiet
docker compose up -d --build web-ui
docker compose ps web-ui
curl --fail --silent http://127.0.0.1:8501/_stcore/health
docker compose logs --tail=100 web-ui
```

Ожидаемый health response — `ok`, а состояние сервиса в `docker compose ps` —
`healthy`. После подключения в UI вручную проверьте:

1. создание ready one-prompt спецификации;
2. тестовый запуск из карточки;
3. скачивание обоих JSON-файлов;
4. отсутствие API-ключа и folder ID в runtime JSON;
5. понятное сообщение для недоступного RAG-индекса.

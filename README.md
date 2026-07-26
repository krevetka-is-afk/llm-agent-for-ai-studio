# llm-agent-for-ai-studio

MVP ассистента, который помогает спроектировать one-prompt или RAG-приложение
и создаёт необходимые ресурсы в Yandex AI Studio. Завершённый сценарий
возвращает валидированную `AgentSpecification`, позволяет выполнить один
stateless тестовый запрос через Responses API и скачать как исходную
спецификацию, так и исполняемый runtime config. One-prompt может включать
встроенный `web_search`, а RAG-вариант использует созданный vector store через
нативный `file_search`.

Основной пользовательский интерфейс — Streamlit Web UI. Telegram-бот и OAuth
Gateway сохранены как экспериментальные адаптеры и не запускаются по умолчанию.
MVP не создаёт постоянную Agent Atelier entity и не возвращает `agent_id`.

## Быстрый запуск Web UI

Требования: Python 3.13 и `uv`.

```bash
uv sync --frozen
cp .env.web.example .env.web
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode("ascii"))'
```

Скопируйте полученный ключ в `YC_API_KEY_ENCRYPTION_KEY` внутри `.env.web`, затем
запустите приложение:

```bash
PYTHONPATH=src uv run --env-file .env.web streamlit run src/ui/app.py
```

Локальные базы и загруженные файлы сохраняются в `.local/`; этот каталог
исключён из Git. В Docker Compose те же данные сохраняются в volume `web-data`.

Пользователь вводит API-ключ Yandex AI Studio и ID каталога. Ключ проверяется
минимальным запросом и хранится локально в зашифрованном виде; в model/tool
context он не передаётся.

Готовую карточку агента можно:

1. протестировать на произвольном запросе;
2. проверить ответ, источники, понятные метрики токенов и `response_id` с
   tooltip-справкой;
3. скачать `agent-specification.json`;
4. по no-code инструкции перенести готовые настройки в Agent Atelier;
5. скачать `responses-agent-config.json` или ZIP-пакет для разработчика.

## Архитектура

```text
src/
├── ai_interaction_service.py   # единый application service и transaction boundary
├── agent_specification.py      # формальная JSON-спецификация создаваемого агента
├── agent_runtime.py            # pure compiler в provider-neutral runtime config
├── agent_runner.py             # port, preview и безопасная taxonomy ошибок
├── yandex_responses_runner.py  # adapter Yandex Responses API
├── component_catalog.py        # каталог шаблонов и компонентов MVP
├── credentials.py             # credentials и OpenAI client factories
├── conversation_state.py      # route, draft/latest specification и commit boundary
├── routing.py                 # deterministic overrides for explicit route choices
├── request_context.py         # least-privilege tool context
├── user_store.py              # in-memory Telegram credentials + TTL
├── context.py                 # compatibility re-exports
├── custom_agents/             # coordinator, RAG и one-prompt агенты
├── ui/                        # Streamlit entrypoint и изолированные UI-модули
└── experimental/oauth/        # замороженный OAuth-прототип
```

Подробности и границы модулей: [docs/architecture.md](docs/architecture.md).

## Документация

- [Web UI и подключение](docs/web-ui.md)
- [Архитектура](docs/architecture.md)
- [Требования к MVP](docs/requirements.md)
- [AgentSpecification](docs/agent-specification.md)
- [Исполнение спецификации через Responses API](docs/agent-runtime.md)
- [Каталог компонентов](docs/component-catalog.md)
- [Тестирование и credentialed E2E](docs/testing.md)
- [Docker и deployment](docs/deployment.md)
- [Экспериментальный Telegram-бот](docs/telegram-experimental.md)
- [Экспериментальный OAuth Gateway](docs/oauth-gateway-experimental.md)

## Проверка перед коммитом

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
uv run pre-commit run --all-files
```

Credentialed E2E является opt-in, использует отдельный короткоживущий ключ и
может расходовать квоту. Обычный `pytest` не обращается к Yandex AI Studio.

## Docker

```bash
cp .env.web.example .env.web
docker compose up -d --build
```

Контейнер запускается от non-root пользователя с read-only root filesystem,
сброшенными Linux capabilities, healthcheck, лимитом памяти 1 ГБ, лимитом 256
процессов и `no-new-privileges`. Подробности — в
[docs/deployment.md](docs/deployment.md).

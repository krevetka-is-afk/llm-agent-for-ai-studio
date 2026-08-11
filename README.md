# Shada Agent Builder for Yandex AI Studio

Open-source ассистент Shada, который помогает спроектировать one-prompt,
RAG-приложение или сценарий с Code Interpreter и создаёт необходимые ресурсы в
Yandex AI Studio. Завершённый сценарий
возвращает валидированную `AgentSpecification`, позволяет выполнить один
stateless тестовый запрос через Responses API и скачать как исходную
спецификацию, так и исполняемый runtime config. One-prompt может включать
встроенный `web_search`, а RAG-вариант использует созданный vector store через
нативный `file_search`. Оба шаблона могут дополнительно получить переносимую
возможность `code_interpreter`: пользователь явно выбирает файлы для каждого
preview, а созданные артефакты доступны для безопасного скачивания.

Основной пользовательский интерфейс — Streamlit Web UI. Telegram-бот и OAuth
Gateway сохранены как экспериментальные адаптеры и не запускаются по умолчанию.
MVP не создаёт постоянную Agent Atelier entity и не возвращает `agent_id`.

Проект находится в статусе `0.1.x Alpha`. Названия Yandex AI Studio и Yandex
Cloud используются для обозначения совместимости. Партнёрская атрибуция и
визуальные материалы будут опубликованы только после отдельного согласования;
текущие правила описаны в [гайде по бренду](docs/branding.md).

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
uv run --env-file .env.web streamlit run src/ai_studio_agent_builder/entrypoints/web.py
```

Локальные базы и загруженные файлы сохраняются в `.local/`; этот каталог
исключён из Git. В Docker Compose те же данные сохраняются в volume `web-data`.
На POSIX-системах файлы ключей и истории создаются с правами `0600`, каталоги
вложений — `0700`. Неиспользуемые Web-подключения автоматически удаляются из
зашифрованной базы через 30 дней. Локальные файлы ограничены 100 MiB и 100
объектами на user scope, а общий storage root — 512 MiB.

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

Для Code Interpreter файлы карточки preview не смешиваются с файлами
Builder-чата. Каждый запуск имеет собственный upload/download lifecycle:
входы проходят лимиты, временные remote IDs добавляются только в копию запроса,
выходы потоково сохраняются в `.local/`, а известные remote resources удаляются
best effort. Defense-in-depth TTL ограничивает жизнь provider input files 48
часами, а RAG vector stores — одним днём. API-ключи, folder ID, пользовательские
bytes и временные file/container IDs в экспорт и ZIP не попадают.

Готовую `agent-specification.json` также можно приложить в чат с запросом
«создай агента из этой спецификации». Приложение строго проверит JSON и схему,
импортирует карточку без повторного создания RAG-индекса; доступность указанного
vector store проверяется при тестовом запуске.

## Архитектура

```text
src/
├── ai_studio_agent_builder/
│   ├── domain/                # спецификация, каталог, routing и runtime compiler
│   ├── application/           # use cases, DTO, errors и порты
│   ├── builder/               # orchestration builder-агентов и tools
│   ├── infrastructure/        # Yandex AI Studio, persistence и observability
│   ├── presentation/
│   │   ├── streamlit/         # Web UI
│   │   └── telegram/          # экспериментальный Telegram adapter
│   ├── entrypoints/           # тонкие Web/Telegram bootstraps
│   ├── experimental/oauth/    # изолированный OAuth-прототип
│   └── composition.py         # composition root
```

Подробности и границы модулей: [docs/architecture.md](docs/architecture.md).

## Документация

- [Web UI и подключение](docs/web-ui.md)
- [Архитектура](docs/architecture.md)
- [Требования к MVP](docs/requirements.md)
- [AgentSpecification](docs/agent-specification.md)
- [Исполнение спецификации через Responses API](docs/agent-runtime.md)
- [Пример Code Interpreter](examples/code-interpreter/README.md)
- [Каталог компонентов](docs/component-catalog.md)
- [Тестирование и credentialed E2E](docs/testing.md)
- [Docker и deployment](docs/deployment.md)
- [Бренд и внешняя атрибуция](docs/branding.md)
- [Чек-лист публичного релиза](docs/release-checklist.md)
- [Отчёт о готовности к публичному релизу](docs/release-readiness.md)
- [Экспериментальный Telegram-бот](docs/telegram-experimental.md)
- [Экспериментальный OAuth Gateway](docs/oauth-gateway-experimental.md)

## Проверка перед коммитом

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
uv build --wheel --sdist
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

## Участие в проекте

Перед изменениями прочитайте [CONTRIBUTING.md](CONTRIBUTING.md) и
[GOVERNANCE.md](GOVERNANCE.md). Ошибки и предложения оформляются через GitHub
Issues. Уязвимости нельзя публиковать в issues — используйте приватный процесс
из [SECURITY.md](SECURITY.md).

## Лицензия

Исходный код распространяется по лицензии MIT. Полный текст находится в
[LICENSE](LICENSE). Лицензия на код не предоставляет прав на товарные знаки или
на заявления от имени Shada, Yandex либо Yandex Cloud.

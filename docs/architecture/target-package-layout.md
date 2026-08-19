# Структура Python package

```text
src/ai_studio_agent_builder/
├── domain/                 # спецификация, каталог, routing, runtime
├── application/            # сценарии, DTO, политики и порты
├── builder/                # агенты, tools и result assembly
├── infrastructure/
│   ├── yandex_ai_studio/   # Responses, Files и connection adapters
│   ├── persistence/        # SQLite и локальные файлы
│   └── observability/      # logging
├── presentation/
│   ├── streamlit/
│   └── telegram/
├── entrypoints/
├── experimental/oauth/
├── config.py
└── composition.py
```

Небольшие связанные классы остаются в одном модуле. Общие `utils.py`,
`helpers.py` и `common.py` не используются: повторно применяемая логика должна
иметь конкретного владельца.

## Правила зависимостей

| Source | Разрешённые package dependencies |
| --- | --- |
| `domain` | `domain`, stdlib |
| `application` | `domain`, `application` |
| `builder` | `domain`, `application`, `builder` |
| `infrastructure` | `domain`, application ports, `infrastructure` |
| `presentation` | domain DTO, `application`, `presentation` |
| `entrypoints` | `composition`, `presentation`, `entrypoints` |

Дополнительные ограничения:

- `domain` не импортирует внешние библиотеки;
- `application` не импортирует Agents SDK, provider SDK и UI frameworks;
- provider SDK разрешён только в `builder/agents` и `infrastructure`;
- `presentation` не обращается к provider clients напрямую;
- циклы между package modules запрещены;
- `composition.py` — единственное место, где связываются конкретные реализации.

Эти правила проверяет `tests/test_architecture.py` через разбор Python AST.

## Основные границы

- `application/ports/builder_run.py` отделяет сценарий диалога от Agents SDK.
- `application/ports/agent_runner.py` отделяет preview от Responses API.
- `application/ports/file_resource_gateway.py` отделяет файловый lifecycle от
  Files API.
- `application/ports/api_key_store.py` и `connection.py` отделяют UI от
  persistence и проверки credentials.

Порты создаются только на границе внешней системы или отдельного слоя. Для
внутренних pure-функций дополнительные интерфейсы не нужны.

## Публичный Python API

В `0.1.0` стабильными считаются:

- `AgentSpecification` и связанные value objects;
- strict JSON load/dump helpers;
- `ExecutableAgentConfig` и runtime compiler.

Builder agents, Yandex adapters, persistence, UI и experimental modules не
реэкспортируются из package root.

## Проверка структуры

```bash
uv run pytest -q tests/test_architecture.py tests/test_package_contract.py \
  tests/test_distribution_artifact.py
uv build --wheel --sdist
```

Тесты проверяют направление импортов, отсутствие циклов, package exports и
установку wheel/sdist вне repository root.

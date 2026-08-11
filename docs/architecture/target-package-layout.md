# Целевая структура Python package

## Решение

Production-код перенесён из flat `src/*.py` в installable package
`ai_studio_agent_builder`. Завершённая инкрементальная миграция не изменила
пользовательское поведение или JSON-контракт `AgentSpecification 1.0`.

```text
src/ai_studio_agent_builder/
├── domain/
│   ├── catalog.py
│   ├── specification.py
│   ├── specification_codec.py
│   ├── runtime.py
│   ├── artifacts.py
│   └── routing.py
├── application/
│   ├── dto.py
│   ├── builder_service.py
│   ├── preview_service.py
│   ├── file_lifecycle.py
│   └── ports/
│       ├── agent_runner.py
│       ├── builder_runner.py
│       └── file_resource_gateway.py
├── builder/
│   ├── agents/
│   ├── tools/
│   └── result_assembly.py
├── infrastructure/
│   ├── yandex_ai_studio/
│   │   ├── client_factory.py
│   │   ├── responses_runner.py
│   │   ├── files_gateway.py
│   │   └── vector_index.py
│   ├── persistence/
│   └── observability/
├── presentation/
│   ├── streamlit/
│   └── telegram/
├── entrypoints/
│   ├── web.py
│   └── telegram.py
├── experimental/
├── config.py
└── composition.py
```

Дерево задаёт границы, а не one-class-per-file. Связанные небольшие value
objects и errors остаются в модуле своего cohesive contract. Generic
`utils.py`, `helpers.py`, `common.py` и catch-all `service.py` не создаются.

## Карта текущих модулей

| Current path | Target path | Примечание |
| --- | --- | --- |
| `component_catalog.py` | `domain/catalog.py` | Pure catalog |
| `agent_specification.py` | `domain/specification.py`, `domain/specification_codec.py` | Model/validation отдельно от strict parsing/serialization |
| `agent_runtime.py` | `domain/runtime.py` | Provider-neutral compile contract; принимает domain runtime settings, не импортирует `config.py` |
| `routing.py` | `domain/routing.py` | Deterministic pure routing |
| `agent_runner.py` | `application/ports/agent_runner.py` | Port и normalized DTO/errors |
| `ai_interaction_service.py` | `application/builder_service.py`, `preview_service.py`, `file_lifecycle.py`, `dto.py`, `ports/builder_runner.py` | Разделить use cases; application вызывает Builder только через port |
| `conversation_state.py` | `application/builder_state.py` | Transactional working state |
| `request_context.py` | `builder/context.py` + application ports | Убрать concrete `OpenAI` client; оставить least-privilege context |
| `context.py` | Временный root compatibility shim | Не переносить в package; удалить после миграции всех imports до `v0.1.0` |
| `result_assembly.py` | `builder/result_assembly.py`, `builder/agents/sdk_event_adapter.py` | Assembly принимает normalized events, SDK event parsing изолирован |
| `custom_agents/` | `builder/agents/`, `builder/tools/` | Agents SDK adapter layer |
| `yandex_responses_runner.py` | `infrastructure/yandex_ai_studio/responses_runner.py` | Provider adapter |
| `credentials.py` | `infrastructure/yandex_ai_studio/client_factory.py` + credential input в `application/dto.py` | SDK clients и secrets не входят в domain |
| `custom_agents/tools/upload_files.py` | `application/file_policy.py` + `infrastructure/yandex_ai_studio/files_gateway.py` | Path/quota policy отделить от provider create/read/delete |
| `file_security.py` | `application/file_policy.py` | Pure filename/path policy; disk/provider I/O снаружи |
| `session.py` | `infrastructure/persistence/agent_sessions.py` | Agents SDK SQLite session adapter |
| `logging_config.py` | `infrastructure/observability/logging.py` | Redacted structured logging setup |
| `config.py` | `config.py` | Typed configuration, без composition side effects |
| `message_service.py` | `presentation/telegram/messages.py` | Telegram-specific rendering |
| `bot_handlers.py` | `presentation/telegram/handlers.py` | Experimental adapter |
| `bot_utils.py` | `presentation/telegram/media.py` + shared `application/file_policy.py` | Telegram parsing отдельно от safe filenames |
| `telegram_flow.py` | `presentation/telegram/request_gate.py` | Adapter concurrency control |
| `telegram_session.py` | `presentation/telegram/http_session.py` | Aiogram HTTP adapter |
| `user_store.py` | `infrastructure/persistence/telegram_user_store.py` | Experimental in-memory credentials/state store |
| `app.py` | `entrypoints/telegram.py` | Thin executable bootstrap; experimental |
| `ui/app.py` | `entrypoints/web.py` + `presentation/streamlit/app.py` | Bootstrap отдельно от views/controllers |
| `ui/agent_test_panel.py` | `presentation/streamlit/agent_test_panel.py` | Вызывает preview use case |
| `ui/chat_flow.py` | `presentation/streamlit/chat_flow.py` | Вызывает builder use case |
| `ui/attachments.py`, `ui/uploads.py` | `presentation/streamlit/attachments.py`, `uploads.py` + `application/file_policy.py` | UI policy не authoritative |
| `ui/connection.py`, `ui/api_key_store.py` | `presentation/streamlit/connection.py` + `infrastructure/persistence/api_key_store.py` | Удалить дублирование ownership |
| `ui/developer_bundle.py`, `ui/result_view.py`, `ui/user_guidance.py` | Одноимённые модули в `presentation/streamlit/` | Presentation-only |
| `experimental/oauth/` | `experimental/oauth/` внутри package + отдельный experimental entrypoint | Не входит в public API |

## Dependency contract

Architecture test строит import graph через stdlib `ast` и проверяет:

| Source | Может импортировать | Не может импортировать |
| --- | --- | --- |
| `domain` | `domain`, stdlib | application, builder, infrastructure, presentation, SDK |
| `application` | domain, application | infrastructure, presentation, composition |
| `builder/agents` | domain, application, builder, Agents SDK | presentation, concrete persistence/provider clients |
| `builder` вне `builder/agents` | domain, application, builder normalized events | Agents SDK, presentation, concrete persistence |
| `infrastructure` | domain, application ports, infrastructure, provider SDK | presentation |
| `presentation` | domain DTO, application, presentation | provider SDK/adapters |
| `entrypoints` | composition, presentation | domain behavior и provider calls напрямую |
| `composition` | все необходимые concrete modules | — |

Цикл между package modules является ошибкой независимо от слоя.

## Public surface `v0.1.0`

Публичными считаются только явно реэкспортированные contracts:

- `AgentSpecification` и связанные domain value objects;
- strict load/dump helpers с версией схемы;
- `ExecutableAgentConfig` и compile function;
- provider-neutral preview DTO/errors при необходимости внешней интеграции.

UI, Agents SDK implementation, Yandex adapters, stores и experimental modules
не являются стабильным public API. `__init__.py` не должен реэкспортировать
внутренние реализации ради удобства.

## Выполненная последовательность миграции

1. Добавить PEP 517 build backend и пустой package skeleton.
2. Перенести domain/catalog/specification/runtime/routing без изменения логики.
3. Добавить compatibility imports только там, где они нужны для следующего
   механического шага; новый код использует package imports.
4. Выделить application DTO/ports и разделить builder/preview use cases.
   `BuilderConversationService` получает `BuilderRunPort`, не импортирует
   concrete agents или result assembly.
5. Перенести Yandex/persistence adapters и запретить provider type leakage.
6. Перенести builder agents/tools; нормализовать Agents SDK events в
   `builder/agents/sdk_event_adapter.py` до передачи в result assembly и
   реализовать application-owned `BuilderRunPort`.
7. Перенести presentation и добавить thin entrypoints, единственные, кому
   разрешён импорт composition root.
8. Обновить Docker, Compose, README и test commands.
9. Удалить compatibility modules и доказать отсутствие второго import tree.

После каждого шага выполняются `ruff`, `ty`, полный `pytest` и relevant Docker
smoke. Feature-поведение Code Interpreter начинается только после зелёной
package foundation.

## Definition of done

- `uv sync --locked` устанавливает package;
- import работает из wheel/sdist и вне repository root;
- test/runtime команды не зависят от `PYTHONPATH=src`;
- architecture test ловит запрещённый import и cycle;
- все entrypoints и Docker healthchecks проходят;
- `AgentSpecification 1.0` совместима;
- flat production modules и временные shims удалены до `v0.1.0`;
- `graphify update .` показывает те же направления зависимостей, что ADR.

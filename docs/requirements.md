# Требования к MVP Agent Builder

Документ фиксирует проверяемые требования к MVP Agent Builder для практики.
Текущий результат MVP — переносимая `AgentSpecification`, system prompt и, для
RAG-сценария, созданный ресурс vector index в Yandex AI Studio. MVP не является
полноценным marketplace компонентов и не создаёт отдельную постоянную remote
agent entity.

## Цель и место в AI Studio

Agent Builder — прикладной слой поверх AI Studio, который помогает пользователю
пройти от естественного запроса к проверяемой конфигурации будущего
LLM-приложения. AI Studio предоставляет модели, встроенный Web Search, файлы,
vector stores и API-совместимый интерфейс; Agent Builder управляет
пользовательским сценарием, валидацией, сборкой результата и экспортом
спецификации.

## Границы MVP

Входит в MVP:

- Streamlit Web UI как основной интерфейс;
- coordinator для выбора сценария;
- one-prompt template;
- опциональный built-in `web_search` для one-prompt;
- RAG template с загрузкой файлов и созданием vector index;
- минимальный каталог компонентов;
- `AgentSpecification` с JSON-экспортом;
- детерминированная валидация обязательных полей;
- локальные tests, lint, typecheck и opt-in credentialed E2E.

Не входит в MVP:

- визуальный drag-and-drop builder;
- marketplace шаблонов и сторонних инструментов;
- постоянное облачное хранилище спецификаций;
- production OAuth flow;
- multi-replica coordination;
- создание отдельной remote agent entity сверх system prompt/vector index.

## Акторы

- Пользователь Agent Builder — формулирует задачу будущего агента, загружает
  файлы и получает результат.
- Agent Builder application service — маршрутизирует сценарий, запускает
  агентов, создаёт AI Studio resources и собирает typed result.
- AI Studio — выполняет model calls, хранит файлы и создаёт vector stores.
- Разработчик/проверяющий — запускает tests, анализирует документацию и
  воспроизводит MVP.

## Use cases

### UC-01. Создание one-prompt агента

Пользователь описывает простое LLM-приложение без базы знаний. Система
формирует system prompt, создаёт `AgentSpecification` с шаблоном `one_prompt` и
позволяет скачать JSON. Если пользователь подтверждает потребность в актуальной
информации из интернета, спецификация дополнительно получает публичный
`web_search`; `knowledge_sources` остаётся пустым.

### UC-02. Создание RAG-агента

Пользователь загружает файлы или явно просит RAG/базу знаний. Система загружает
файлы в AI Studio, создаёт vector index, формирует system prompt,
`knowledge_search` tool descriptor и экспортируемую `AgentSpecification`.

### UC-03. Автоматический выбор шаблона

Явный запрос vector RAG, индекса или индексации приложенных файлов выбирает
`rag`. Web search или внешнее API без пользовательской базы документов выбирают
`one_prompt`. Последний явный отказ пользователя от RAG имеет приоритет над
предыдущим route; неоднозначные требования уточняет coordinator.

### UC-04. Уточнение недостающих параметров

Если обязательные поля спецификации отсутствуют, валидатор возвращает полный
список `missing_fields`, а спецификация получает статус `needs_clarification`.

### UC-05. Проверка и экспорт результата

UI показывает typed result parts: vector index, agent specification и markdown.
Пользователь может скачать `AgentSpecification` как JSON.

## Функциональные требования

| ID | Требование | Acceptance criteria |
| --- | --- | --- |
| FR-01 | Система должна принимать текстовый запрос пользователя и вложения через Web UI. | Запрос преобразуется в `InteractionRequest`; ограничения количества и размера файлов проверяются до обращения к AI Studio. |
| FR-02 | Система должна маршрутизировать запрос в coordinator, RAG или one-prompt agent по состоянию диалога и последнему явному выбору пользователя. | Явный отказ от vector RAG переключает sticky RAG route в `ONE_PROMPT`; web search без vector knowledge не считается RAG; ambiguous intent остаётся coordinator. |
| FR-03 | Система должна создавать RAG vector index только из файлов текущего запроса. | `create_search_index` отклоняет пустые, дублирующиеся и неразрешённые `file_id`. |
| FR-04 | Система должна собирать authoritative typed result из tool calls, а не только из текста модели. | `ResultAssembler` создаёт `VectorIndexResultPart` из `create_search_index` call/output. |
| FR-05 | Система должна формировать `AgentSpecification` для завершённого результата пользователя. | `AgentSpecificationResultPart` появляется только после успешного вызова `finalize_agent_specification` и готовой валидации. |
| FR-06 | `AgentSpecification` должна содержать назначение, входы, инструкции, ограничения, источники знаний, tools и expected result. | JSON-экспорт содержит поля `purpose`, `inputs`, `instructions`, `constraints`, `knowledge_sources`, `tools`, `expected_result`. |
| FR-07 | Система должна валидировать обязательные поля спецификации детерминированно. | Пустая/неполная spec получает `needs_clarification`; валидатор возвращает все `missing_fields`. |
| FR-08 | RAG-спецификация должна содержать knowledge source и публичный `knowledge_search` tool, связанный с `index_id`. | Полная RAG spec содержит `knowledge_sources`, `parameters.index_id` и `tools[].tool_id == "knowledge_search"` с тем же `index_id`. |
| FR-09 | Система должна экспортировать спецификацию в JSON без секретов. | UI показывает download button; `to_record()` заменяет значения secret-like parameter keys на `[REDACTED]`, а валидатор не допускает такую spec в статус `ready`. |
| FR-10 | Внутренние orchestration tools не должны выдаваться за прикладные tools будущего агента. | В catalog/docs `delegate_*`, `finish_dialog`, `create_search_index`, `update_agent_specification` и `finalize_agent_specification` отделены от public `knowledge_search` и `web_search`. |
| FR-11 | One-prompt-спецификация должна отражать подтверждённую потребность в веб-поиске. | `web_search=true` идемпотентно добавляет публичный descriptor с `search_context_size=medium`; `None` сохраняет выбор, `false` удаляет его; `knowledge_sources` остаётся пустым. |

## Нефункциональные требования

| ID | Требование | Acceptance criteria |
| --- | --- | --- |
| NFR-01 | API-ключ не должен попадать в model/tool context, результат или JSON spec. | `RequestContext` не содержит `api_key`; secret-like параметры редактируются при сериализации. |
| NFR-02 | Ошибки пользователя и AI Studio должны отображаться безопасно. | UI возвращает bounded сообщения без внутренних stack traces и secret details. |
| NFR-03 | Изменение состояния диалога и черновика спецификации должно быть транзакционным. | `ConversationState.commit_from()` вызывается только после успешного agent run и сборки результата; ошибка не коммитит route/draft/latest spec. |
| NFR-04 | Upload flow должен иметь ограниченный blast radius. | Файлы сохраняются в пользовательской директории, имена санитизируются, лимиты проверяются. |
| NFR-05 | Результат должен быть воспроизводимым для отчёта и проверки. | Есть docs по архитектуре, схеме spec, каталогу, testing и test results. |
| NFR-06 | Проверка качества должна быть автоматизируемой. | Поддерживаются `ruff format --check`, `ruff check`, `ty check`, `pytest -q`, `pre-commit`. |
| NFR-07 | Credentialed E2E не должен запускаться случайно. | Тест помечен `yandex_ai_studio_e2e` и требует explicit env flag. |
| NFR-08 | MVP должен оставаться малым и проверяемым. | Новые функции реализованы без новых production dependencies и без marketplace scope. |
| NFR-09 | Внутренний model/tool flow должен иметь ограниченный, настраиваемый бюджет turns. | `ModelConfig.max_turns` передаётся в SDK Runner; значение по умолчанию и production config равны 20. |

## Трассировка

| Требование | Модуль | Тест/проверка |
| --- | --- | --- |
| FR-01 | `src/ui/chat_flow.py`, `src/ui/uploads.py`, `src/ai_interaction_service.py` | `tests/test_ui_helpers.py`, `tests/test_ui_smoke.py`, `tests/test_ai_interaction_service.py` |
| FR-02 | `src/routing.py`, `src/ai_interaction_service.py`, `src/conversation_state.py`, `src/custom_agents/coordinator_agent.py` | `tests/test_routing.py`, `tests/test_ai_interaction_service.py`, `tests/test_prompt_quality.py` |
| FR-03 | `src/custom_agents/tools/vector_index.py` | `tests/test_vector_index.py` |
| FR-04 | `src/result_assembly.py` | `tests/test_result_assembly.py` |
| FR-05 | `src/custom_agents/tools/agent_specification.py`, `src/result_assembly.py`, `src/agent_specification.py` | `tests/test_agent_specification_tools.py`, `tests/test_result_assembly.py`, `tests/test_ai_interaction_service.py` |
| FR-06 | `src/agent_specification.py` | `tests/test_agent_specification.py` |
| FR-07 | `src/agent_specification.py`, `src/component_catalog.py` | `tests/test_agent_specification.py` |
| FR-08 | `src/custom_agents/tools/vector_index.py`, `src/agent_specification.py` | `tests/test_vector_index.py`, `tests/test_agent_specification_tools.py`, `tests/test_agent_specification.py` |
| FR-09 | `src/agent_specification.py`, `src/ui/result_view.py` | `tests/test_agent_specification.py`; UI smoke вручную/Streamlit |
| FR-10 | `src/component_catalog.py`, `docs/component-catalog.md` | `tests/test_agent_specification.py` |
| FR-11 | `src/custom_agents/one_prompt_agent.py`, `src/custom_agents/tools/agent_specification.py`, `src/agent_specification.py` | `tests/test_prompt_quality.py`, `tests/test_agent_specification_tools.py`, `tests/test_agent_specification.py` |
| NFR-01 | `src/request_context.py`, `src/agent_specification.py` | `tests/test_context.py`, `tests/test_agent_specification.py` |
| NFR-02 | `src/ui/chat_flow.py` | `tests/test_ui_helpers.py` |
| NFR-03 | `src/conversation_state.py`, `src/ai_interaction_service.py` | `tests/test_context_compat.py`, `tests/test_ai_interaction_service.py` |
| NFR-04 | `src/file_security.py`, `src/ui/uploads.py`, `src/ai_interaction_service.py` | `tests/test_upload_file_security.py`, `tests/test_ui_smoke.py` |
| NFR-05 | `docs/*.md`, `docs/report/*.typ` | Документальная проверка |
| NFR-06 | `pyproject.toml`, `.pre-commit-config.yaml` | Quality gate commands |
| NFR-07 | `tests/e2e/test_yandex_ai_studio_rag_e2e.py` | `pytest` skip без env; opt-in запуск с credentials |
| NFR-08 | `pyproject.toml`, code review | `uv run pytest -q`, `uv run ty check`, dependency diff |
| NFR-09 | `src/config.py`, `src/custom_agents/base_agent.py`, `config.yaml` | `tests/test_base_agent.py`, `tests/test_config.py` |

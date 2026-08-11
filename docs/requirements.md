# Требования к MVP Agent Builder

Документ фиксирует проверяемые требования к MVP Agent Builder для практики.
Текущий результат MVP — переносимая `AgentSpecification`, проверяемая
runtime-конфигурация для Responses API, stateless test run и, для RAG-сценария,
созданный vector store в Yandex AI Studio. MVP не является полноценным
marketplace компонентов и не создаёт отдельную постоянную remote agent entity.

## Цель и место в AI Studio

Agent Builder — прикладной слой поверх AI Studio, который помогает пользователю
пройти от естественного запроса к проверяемой конфигурации будущего
LLM-приложения. AI Studio предоставляет модели, встроенный Web Search, файлы,
vector stores и API-совместимый интерфейс; Agent Builder управляет
пользовательским сценарием, валидацией, сборкой результата, тестовым запуском и
экспортом спецификации вместе с её исполняемой runtime-конфигурацией.

## Границы MVP

Входит в MVP:

- Streamlit Web UI как основной интерфейс;
- coordinator для выбора сценария;
- one-prompt template;
- опциональный built-in `web_search` для one-prompt;
- RAG template с загрузкой файлов и созданием vector index;
- минимальный каталог компонентов;
- `AgentSpecification` с JSON-экспортом;
- строгий импорт сериализованной спецификации и компиляция в runtime config;
- stateless тестирование готового агента через Responses API;
- отображение ответа, citations, usage и `response_id`;
- JSON-экспорт фактически проверенной runtime-конфигурации;
- детерминированная валидация обязательных полей;
- локальные tests, lint, typecheck и opt-in credentialed E2E.

Не входит в MVP:

- визуальный drag-and-drop builder;
- marketplace шаблонов и сторонних инструментов;
- постоянное облачное хранилище спецификаций;
- production OAuth flow;
- multi-replica coordination;
- долговременная история тестовых запросов и streaming-ответы;
- автоматическое восстановление удалённого или истёкшего vector store;
- создание отдельной remote agent entity сверх system prompt/vector index.

## Акторы

- Пользователь Agent Builder — формулирует задачу будущего агента, загружает
  файлы и получает результат.
- Agent Builder application service — маршрутизирует сценарий, запускает
  агентов, создаёт AI Studio resources, собирает typed result, компилирует
  runtime-конфигурацию и выполняет stateless preview.
- AI Studio — выполняет model calls и Responses API calls, хранит файлы и
  создаёт vector stores.
- Разработчик/проверяющий — запускает tests, анализирует документацию и
  воспроизводит MVP.

## Use cases

### UC-01. Создание one-prompt агента

Пользователь описывает простое LLM-приложение без базы знаний. Система
формирует system prompt, создаёт `AgentSpecification` с шаблоном `one_prompt` и
позволяет проверить агента и скачать оба JSON-представления. Если пользователь
подтверждает потребность в актуальной информации из интернета, спецификация
дополнительно получает публичный `web_search`; runtime использует одноимённый
built-in tool, а `knowledge_sources` остаётся пустым.

### UC-02. Создание RAG-агента

Пользователь загружает файлы или явно просит RAG/базу знаний. Система загружает
файлы в AI Studio, создаёт vector index, формирует system prompt,
`knowledge_search` tool descriptor и экспортируемую `AgentSpecification`.
Runtime-компилятор преобразует descriptor в built-in `file_search` с тем же
`vector_store_id`; перед Responses API call ресурс проверяется через preflight.

### UC-03. Автоматический выбор шаблона

Явный запрос vector RAG, индекса или индексации приложенных файлов выбирает
`rag`. Web search или внешнее API без пользовательской базы документов выбирают
`one_prompt`. Последний явный отказ пользователя от RAG имеет приоритет над
предыдущим route; неоднозначные требования уточняет coordinator.

### UC-04. Уточнение недостающих параметров

Если обязательные поля спецификации отсутствуют, валидатор возвращает полный
список `missing_fields`, а спецификация получает статус `needs_clarification`.

### UC-05. Просмотр и экспорт результата

UI показывает typed result parts: vector index, agent specification и markdown.
Для готовой спецификации пользователь может открыть JSON и скачать
`AgentSpecification`.

### UC-06. Stateless-тест готового агента

Пользователь вводит отдельный тестовый запрос в карточке готового агента.
Система строго восстанавливает спецификацию, компилирует её в runtime config,
выполняет один Responses API call и показывает ответ, citations, usage и
`response_id`. Пользователь может открыть и скачать тот же runtime JSON, который
использовался для запуска. Тест не меняет состояние диалога Agent Builder.

## Функциональные требования

| ID | Требование | Acceptance criteria |
| --- | --- | --- |
| FR-01 | Система должна принимать текстовый запрос пользователя и вложения через Web UI. | Запрос преобразуется в `InteractionRequest`; ограничения количества и размера файлов проверяются до обращения к AI Studio. |
| FR-02 | Система должна маршрутизировать запрос в coordinator, RAG или one-prompt agent по состоянию диалога и последнему явному выбору пользователя. | Явный отказ от vector RAG переключает sticky RAG route в `ONE_PROMPT`; web search без vector knowledge не считается RAG; ambiguous intent остаётся coordinator. |
| FR-03 | Система должна создавать RAG vector index только из файлов, зарегистрированных сервисом для текущего RAG-сценария. | `file_id` отсутствует в tool schema; ожидающие файлы сохраняются между сообщениями в `ConversationState`, потребляются после создания индекса, а вызов без файлов возвращает контролируемый `needs_files`. |
| FR-04 | Система должна собирать authoritative typed result из tool calls, а не только из текста модели. | `ResultAssembler` создаёт `VectorIndexResultPart` только из структурированного успешного `create_search_index` output и не принимает текст ошибки за `index_id`. |
| FR-05 | Система должна формировать `AgentSpecification` для завершённого результата пользователя. | `AgentSpecificationResultPart` появляется только после успешного вызова `finalize_agent_specification` и готовой валидации. |
| FR-06 | `AgentSpecification` должна содержать назначение, входы, инструкции, ограничения, источники знаний, tools и expected result. | JSON-экспорт содержит поля `purpose`, `inputs`, `instructions`, `constraints`, `knowledge_sources`, `tools`, `expected_result`. |
| FR-07 | Система должна валидировать обязательные поля спецификации детерминированно. | Пустая/неполная spec получает `needs_clarification`; валидатор возвращает все `missing_fields`. |
| FR-08 | RAG-спецификация должна содержать knowledge source и публичный `knowledge_search` tool, связанный с `index_id`. | Полная RAG spec содержит `knowledge_sources`, `parameters.index_id` и `tools[].tool_id == "knowledge_search"` с тем же `index_id`. |
| FR-09 | Система должна экспортировать спецификацию в JSON без секретов. | UI показывает download button; `to_record()` заменяет значения secret-like parameter keys на `[REDACTED]`, а валидатор не допускает такую spec в статус `ready`. |
| FR-10 | Внутренние orchestration tools не должны выдаваться за прикладные tools будущего агента. | В catalog/docs `delegate_*`, `finish_dialog`, `create_search_index`, `update_agent_specification` и `finalize_agent_specification` отделены от public `knowledge_search` и `web_search`. |
| FR-11 | One-prompt-спецификация должна отражать подтверждённую потребность в веб-поиске. | `web_search=true` идемпотентно добавляет публичный descriptor с `search_context_size=medium`; `None` сохраняет выбор, `false` удаляет его; `knowledge_sources` остаётся пустым. |
| FR-12 | Система должна строго восстанавливать доменную спецификацию из сериализованной записи перед исполнением. | Неизвестные поля, некорректные типы, неподдерживаемая версия схемы и неготовый статус приводят к контролируемой ошибке до обращения к провайдеру. |
| FR-13 | Система должна детерминированно компилировать готовую спецификацию в runtime config. | One-prompt без tools создаёт пустой список tools; `web_search` преобразуется в built-in Web Search; `knowledge_search` преобразуется в `file_search` с тем же `index_id`. |
| FR-14 | Пользователь должен иметь возможность stateless-проверки готового агента. | UI принимает отдельный test prompt, выполняет один Responses API call и показывает output text, citations, usage и `response_id`. |
| FR-15 | Система должна экспортировать без секретов именно ту runtime-конфигурацию, которая используется для теста. | Test callback и runtime JSON callback используют общий `prepare_agent_runtime()`; экспорт не содержит API key и folder URI. |
| FR-16 | RAG-runtime должен проверять доступность vector store до генерации ответа. | Для каждого `file_search.vector_store_id` выполняется retrieve; отсутствующий, недоступный или неготовый ресурс возвращает безопасную прикладную ошибку. |
| FR-17 | Система должна объяснять дальнейший путь нетехническому пользователю. | Sidebar и готовая карточка содержат no-code шаги и официальные ссылки Agent Atelier; после теста UI показывает готовые настройки для ручного переноса и отдельный ZIP-пакет для разработчика. |

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
| NFR-10 | Тест готового агента не должен изменять основной диалог или черновик спецификации. | Preview выполняется отдельным application-service method без `ConversationState.commit_from()`. |
| NFR-11 | Runtime-ошибки и credentials должны оставаться внутри доверенной границы сервиса. | Result view получает callbacks без API key; provider exceptions преобразуются в bounded сообщения без stack trace и secret details. |
| NFR-12 | Preview должен сохраняться между rerun UI только для неизменённой спецификации. | Результат хранится под ключом карточки и сбрасывается при изменении canonical fingerprint спецификации. |
| NFR-13 | Технические данные должны быть понятны без знания API. | UI использует человеческие подписи и hover-help для citations, token usage, `response_id`, runtime config, template и Vector Store ID; developer ZIP явно отделён от основного no-code пути. |
| NFR-14 | Многошаговый RAG flow не должен зависеть от повторной передачи файла пользователем или выбора `file_id` моделью. | Загруженный файл остаётся доступен после уточнения имени индекса; повторное создание переиспользует существующий индекс; внутренние идентификаторы не включаются в prompt агента. |

## Трассировка

Пути модулей ниже указаны относительно
`src/ai_studio_agent_builder/`, если явно не задан другой корень.

| Требование | Модуль | Тест/проверка |
| --- | --- | --- |
| FR-01 | `presentation/streamlit/chat_flow.py`, `uploads.py`, `application/builder_service.py` | `tests/test_ui_helpers.py`, `tests/test_ui_smoke.py`, `tests/test_ai_interaction_service.py` |
| FR-02 | `domain/routing.py`, `application/builder_service.py`, `builder_state.py`, `builder/agents/coordinator_agent.py` | `tests/test_routing.py`, `tests/test_ai_interaction_service.py`, `tests/test_prompt_quality.py` |
| FR-03 | `application/builder_state.py`, `builder_service.py`, `builder/agents/tools/vector_index.py` | `tests/test_builder_state.py`, `tests/test_ai_interaction_service.py`, `tests/test_vector_index.py` |
| FR-04 | `builder/result_assembly.py` | `tests/test_result_assembly.py`, `tests/test_ai_interaction_service.py` |
| FR-05 | `builder/agents/tools/agent_specification.py`, `builder/result_assembly.py`, `domain/specification.py` | `tests/test_agent_specification_tools.py`, `tests/test_result_assembly.py`, `tests/test_ai_interaction_service.py` |
| FR-06 | `domain/specification.py` | `tests/test_agent_specification.py` |
| FR-07 | `domain/specification.py`, `domain/catalog.py` | `tests/test_agent_specification.py` |
| FR-08 | `builder/agents/tools/vector_index.py`, `domain/specification.py` | `tests/test_vector_index.py`, `tests/test_agent_specification_tools.py`, `tests/test_agent_specification.py` |
| FR-09 | `domain/specification.py`, `presentation/streamlit/result_view.py` | `tests/test_agent_specification.py`, `tests/test_ui_smoke.py` |
| FR-10 | `domain/catalog.py`, `docs/component-catalog.md` | `tests/test_agent_specification.py` |
| FR-11 | `builder/agents/one_prompt_agent.py`, `builder/agents/tools/agent_specification.py`, `domain/specification.py` | `tests/test_prompt_quality.py`, `tests/test_agent_specification_tools.py`, `tests/test_agent_specification.py` |
| FR-12 | `domain/specification.py`, `domain/runtime.py` | `tests/test_agent_specification.py`, `tests/test_agent_runtime.py` |
| FR-13 | `domain/runtime.py` | `tests/test_agent_runtime.py` |
| FR-14 | `application/preview_service.py`, `application/ports/agent_runner.py`, `infrastructure/yandex_ai_studio/responses_runner.py`, `presentation/streamlit/agent_test_panel.py` | `tests/test_ai_interaction_service.py`, `tests/test_yandex_responses_runner.py`, `tests/test_ui_helpers.py`, `tests/test_ui_smoke.py` |
| FR-15 | `application/preview_service.py`, `domain/runtime.py`, `presentation/streamlit/agent_test_panel.py` | `tests/test_ai_interaction_service.py`, `tests/test_agent_runtime.py`, `tests/test_ui_smoke.py` |
| FR-16 | `infrastructure/yandex_ai_studio/responses_runner.py` | `tests/test_yandex_responses_runner.py`, `tests/e2e/test_yandex_ai_studio_agent_runtime_e2e.py` |
| FR-17 | `presentation/streamlit/user_guidance.py`, `developer_bundle.py`, `agent_test_panel.py` | `tests/test_ui_smoke.py`, `tests/test_developer_bundle.py`; Playwright visual smoke |
| NFR-01 | `builder/context.py`, `domain/specification.py` | `tests/test_context.py`, `tests/test_agent_specification.py` |
| NFR-02 | `presentation/streamlit/chat_flow.py`, `agent_test_panel.py`, `infrastructure/yandex_ai_studio/responses_runner.py` | `tests/test_ui_helpers.py`, `tests/test_yandex_responses_runner.py` |
| NFR-03 | `application/builder_state.py`, `builder_service.py` | `tests/test_builder_state.py`, `tests/test_ai_interaction_service.py` |
| NFR-04 | `application/file_policy.py`, `presentation/streamlit/uploads.py`, `application/file_lifecycle.py` | `tests/test_upload_file_security.py`, `tests/test_ui_smoke.py` |
| NFR-05 | `docs/*.md`, `docs/report/*.typ` | Документальная проверка |
| NFR-06 | `pyproject.toml`, `.pre-commit-config.yaml` | Quality gate commands |
| NFR-07 | `tests/e2e/test_yandex_ai_studio_rag_e2e.py`, `tests/e2e/test_yandex_ai_studio_agent_runtime_e2e.py` | `pytest` skip без env; opt-in запуск с credentials |
| NFR-08 | `pyproject.toml`, code review | `uv run pytest -q`, `uv run ty check`, dependency diff |
| NFR-09 | `config.py`, `builder/agents/base_agent.py`, `config.yaml` | `tests/test_base_agent.py`, `tests/test_config.py` |
| NFR-10 | `application/builder_service.py`, `presentation/streamlit/chat_flow.py` | `tests/test_ai_interaction_service.py`, `tests/test_ui_smoke.py` |
| NFR-11 | `presentation/streamlit/chat_flow.py`, `agent_test_panel.py`, `infrastructure/yandex_ai_studio/responses_runner.py` | `tests/test_ui_helpers.py`, `tests/test_yandex_responses_runner.py` |
| NFR-12 | `presentation/streamlit/agent_test_panel.py` | `tests/test_ui_helpers.py`, `tests/test_ui_smoke.py` |
| NFR-13 | `presentation/streamlit/agent_test_panel.py`, `result_view.py`, `user_guidance.py` | `tests/test_ui_smoke.py`; Playwright tooltip/visual smoke |
| NFR-14 | `application/builder_state.py`, `builder_service.py`, `builder/agents/tools/vector_index.py`, `builder/result_assembly.py` | `tests/test_builder_state.py`, `tests/test_ai_interaction_service.py`, `tests/test_vector_index.py`, `tests/test_result_assembly.py` |

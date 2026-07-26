# Архитектура MVP

## Основной поток

1. Web UI или Telegram adapter формирует `InteractionRequest` с уникальным
   `request_id`.
2. `AIInteractionService` создаёт clients Yandex AI Studio на границе сервиса.
3. Агент получает `RequestContext` без API-ключа: только client, folder ID,
   директорию файлов, разрешённые file IDs и рабочую копию состояния.
4. `routing.py` до model call применяет только высокоуверенные явные решения:
   отказ от RAG и запрос web-search без vector knowledge направляются в
   one-prompt, а явный запрос RAG/vector index — в RAG. Неоднозначные запросы
   остаются coordinator.
5. Coordinator при необходимости делегирует оставшийся запрос RAG или
   one-prompt агенту. Каждый запуск ограничен настраиваемым `max_turns` (20 по
   умолчанию), чтобы сложный tool flow имел запас, но бесконечный цикл оставался
   ограниченным.
6. Специализированный агент через `update_agent_specification` обновляет
   типизированный черновик, а валидатор возвращает полный список недостающих
   обязательных полей.
7. One-prompt agent при подтверждённой потребности в актуальных данных добавляет
   публичный descriptor `web_search`; это не создаёт vector index и не заполняет
   `knowledge_sources`.
8. RAG tool после создания vector index авторитетно привязывает `index_id`,
   загруженные файлы и публичный `knowledge_search` к черновику.
9. `finalize_agent_specification` публикует только структурно готовую
   спецификацию; обычный markdown модели не интерпретируется как готовый артефакт.
10. `ResultAssembler` собирает текст, vector index и подтверждённую
   `AgentSpecification` из tool executions и рабочего состояния.
11. Route, draft и latest specification коммитятся только после успешной сборки
    результата.
12. Для тестового запуска application service строго восстанавливает
    `AgentSpecification` из result-part записи и повторно вычисляет readiness.
13. Чистый compiler преобразует доменные `web_search`/`knowledge_search` в
    provider-neutral `ExecutableAgentConfig` с нативными
    `web_search`/`file_search`.
14. `YandexResponsesAgentRunner` добавляет folder ID только при формировании
    model URI, выполняет Vector Store preflight и вызывает Responses API.
15. Ответ, citations и usage возвращаются в UI как stateless preview; builder
    conversation state при этом не изменяется.

## Границы модулей

- `credentials.py` — модели credentials и фабрики sync/async OpenAI clients.
- `conversation_state.py` — mutable route, draft/latest specification и
  транзакционные `copy()`/`commit_from()`.
- `routing.py` — детерминированное распознавание только явного выбора между
  one-prompt и vector RAG; ambiguous intent не классифицирует.
- `user_store.py` — экспериментальное in-memory хранилище Telegram-пользователей.
- `request_context.py` — least-privilege context, доступный агентам и tools.
- `component_catalog.py` — каталог шаблонов `one_prompt`/`rag` и компонентов
  `system_prompt`, `web_search`, `vector_index`, `knowledge_search`.
- `agent_specification.py` — переносимое JSON-описание создаваемого агента,
  строгий `from_record()`, статусы `draft`/`needs_clarification`/`ready` и
  детерминированная валидация.
- `agent_runtime.py` — чистая компиляция готовой доменной спецификации в
  версионированный `ExecutableAgentConfig`.
- `agent_runner.py` — provider-neutral port запуска, preview, citations и
  безопасная taxonomy runtime-ошибок.
- `yandex_responses_runner.py` — Responses API adapter, provider model URI,
  File Search preflight и нормализация ответа.
- `context.py` — временный compatibility shim для стабильности старых импортов.
- `ai_interaction_service.py` — application orchestration, uploads, delegation и
  transaction boundary.
- `result_assembly.py` — authoritative tool results, `AgentSpecificationResultPart`
  и их текстовая проекция.
- `custom_agents/tools/agent_specification.py` — детерминированное обновление и
  финализация спецификации через function tools.

Streamlit entrypoint остаётся `src/ui/app.py`, но детали разделены:

- `connection.py` — подключение и lifecycle API-ключа;
- `uploads.py` — чистая валидация upload metadata;
- `attachments.py` — безопасное отображение и скачивание файлов;
- `result_view.py` — карточки типизированных результатов: vector index,
  AgentSpecification и JSON download;
- `agent_test_panel.py` — stateless test form, fingerprinted preview, citations,
  usage и runtime-config download;
- `chat_flow.py` — history, submission, interaction flow и callback boundary,
  через которую result view получает запуск без прямого доступа к credentials.

## Формальная спецификация создаваемого агента

MVP возвращает не только markdown-текст модели, но и typed result part
`agent_specification`. Для `one_prompt` спецификация фиксирует назначение,
system instructions, expected result и, при необходимости, публичный built-in
tool descriptor `web_search`. Для `rag` дополнительно фиксируются knowledge
sources, созданный `index_id`, ограничение TTL индекса и публичный tool descriptor
`knowledge_search`.

Детерминированная валидация отделена от LLM-поведения. Если обязательные поля
отсутствуют, спецификация получает статус `needs_clarification`; готовой она
считается только при пустых `missing_fields` и `issues` и после явного вызова
`finalize_agent_specification`.

`AgentSpecification` остаётся доменным артефактом, а
`ExecutableAgentConfig` — отдельным runtime-контрактом. Благодаря этому модель,
temperature и output budget не смешиваются с подтверждёнными требованиями
пользователя. Подробнее: [agent-runtime.md](agent-runtime.md).

## Осознанно отложено

- полный перенос flat modules в единый installable package;
- постоянное хранение спецификаций за пределами текущей пользовательской сессии;
- постоянное хранилище Telegram accounts и миграции;
- интеграция OAuth Gateway в основной credential flow;
- multi-replica coordination и distributed locks.
- создание постоянной Agent Atelier entity и возврат `agent_id` до появления
  подтверждённого публичного API.

Эти изменения не нужны для текущего MVP и расширили бы blast radius перед
релизом.

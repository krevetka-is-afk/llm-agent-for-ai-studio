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
7. RAG tool после создания vector index авторитетно привязывает `index_id`,
   загруженные файлы и публичный `knowledge_search` к черновику.
8. `finalize_agent_specification` публикует только структурно готовую
   спецификацию; обычный markdown модели не интерпретируется как готовый артефакт.
9. `ResultAssembler` собирает текст, vector index и подтверждённую
   `AgentSpecification` из tool executions и рабочего состояния.
10. Route, draft и latest specification коммитятся только после успешной сборки
   результата.

## Границы модулей

- `credentials.py` — модели credentials и фабрики sync/async OpenAI clients.
- `conversation_state.py` — mutable route, draft/latest specification и
  транзакционные `copy()`/`commit_from()`.
- `routing.py` — детерминированное распознавание только явного выбора между
  one-prompt и vector RAG; ambiguous intent не классифицирует.
- `user_store.py` — экспериментальное in-memory хранилище Telegram-пользователей.
- `request_context.py` — least-privilege context, доступный агентам и tools.
- `component_catalog.py` — каталог шаблонов `one_prompt`/`rag` и компонентов
  `system_prompt`, `vector_index`, `knowledge_search`.
- `agent_specification.py` — переносимое JSON-описание создаваемого агента,
  статусы `draft`/`needs_clarification`/`ready` и детерминированная валидация.
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
- `chat_flow.py` — history, submission и interaction flow.

## Формальная спецификация создаваемого агента

MVP возвращает не только markdown-текст модели, но и typed result part
`agent_specification`. Для `one_prompt` спецификация фиксирует назначение,
system instructions и expected result. Для `rag` дополнительно фиксируются
knowledge sources, созданный `index_id`, ограничение TTL индекса и публичный
tool descriptor `knowledge_search`.

Детерминированная валидация отделена от LLM-поведения. Если обязательные поля
отсутствуют, спецификация получает статус `needs_clarification`; готовой она
считается только при пустых `missing_fields` и `issues` и после явного вызова
`finalize_agent_specification`.

## Осознанно отложено

- полный перенос flat modules в единый installable package;
- постоянное хранение спецификаций за пределами текущей пользовательской сессии;
- постоянное хранилище Telegram accounts и миграции;
- интеграция OAuth Gateway в основной credential flow;
- multi-replica coordination и distributed locks.

Эти изменения не нужны для текущего MVP и расширили бы blast radius перед
релизом.

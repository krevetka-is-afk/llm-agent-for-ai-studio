# Исполнение AgentSpecification

## Назначение

Готовая `AgentSpecification` — доменный результат builder-диалога. Для запуска
она детерминированно компилируется в отдельный `ExecutableAgentConfig`, который
соответствует возможностям Yandex AI Studio Responses API.

```text
serialized result part
        |
        v
AgentSpecification.from_record()
        |
        v
compile_agent_specification()
        |
        v
ExecutableAgentConfig
        |
        v
YandexResponsesAgentRunner
        |
        v
Responses API
```

Разделение не позволяет deployment-параметрам модели подменять подтверждённые
пользователем требования и оставляет доменную JSON-схему переносимой.

## Runtime-контракт

`ExecutableAgentConfig` содержит:

| Поле | Назначение |
| --- | --- |
| `schema_version` | Версия отдельного runtime-контракта. |
| `model_name` | Имя модели без folder ID. |
| `instructions` | Подтверждённые инструкции, constraints и expected result. |
| `tools` | Только нативные Responses API descriptors. |
| `temperature` | Параметр генерации из server-side config. |
| `max_output_tokens` | Server-side лимит ответа. |

API-ключ, Authorization headers, folder ID и полный provider model URI в export
не входят. Приложение формирует `gpt://<folder_id>/<model_name>` только внутри
Yandex adapter непосредственно перед запросом.

Пример экспортируемого конфига:

```json
{
  "instructions": "Search before answering.\n\nExpected result:\nA grounded answer",
  "max_output_tokens": 1000,
  "model_name": "gpt-oss-120b",
  "schema_version": "1.0",
  "temperature": 0.5,
  "tools": [
    {
      "search_context_size": "medium",
      "type": "web_search"
    }
  ]
}
```

Поле `input` отсутствует намеренно: приложение задаёт его отдельно при каждом
stateless-запуске.

## Отображение tools

| AgentSpecification | Responses API |
| --- | --- |
| без tools | поле `tools` не передаётся |
| `web_search` | `{"type": "web_search", "search_context_size": "medium"}` |
| `knowledge_search` с `index_id` | `{"type": "file_search", "vector_store_ids": ["<index_id>"]}` |

Внутренние orchestration tools никогда не попадают в runtime. Для File Search
adapter сначала вызывает `vector_stores.retrieve(index_id)` и не отправляет
Responses API запрос, если индекс отсутствует, истёк или не завершён.

## Application и UI

`AIInteractionService.test_agent_specification()`:

1. ограничивает тестовый input 10 000 символами;
2. строго восстанавливает и повторно валидирует спецификацию;
3. компилирует тот же config, который доступен для скачивания;
4. создаёт client через текущую credential boundary;
5. выполняет sync SDK в `asyncio.to_thread`;
6. возвращает только ответ, citations, token usage и `response_id`.

Метод не принимает `ConversationState` и не изменяет builder-диалог.
Streamlit хранит preview по fingerprint конкретной spec-card; изменение
спецификации инвалидирует старый результат.

Технические поля снабжены tooltip-справкой: отдельно объясняются citations,
input/output/total tokens, `response_id`, runtime config, template и Vector
Store ID. После успешного теста UI предлагает два явно разделённых пути:

1. no-code перенос модели, инструкции, tools и параметров в Agent Atelier;
2. ZIP-пакет для разработчика с обоими JSON, `example.py`, `.env.example` и
   README.

ZIP создаётся в памяти и не содержит API-ключ или folder ID. Ссылки на
официальную инструкцию Agent Atelier доступны как в карточке результата, так и
в sidebar.

## Безопасные ошибки

UI различает:

- недоступный или истёкший Vector Store;
- timeout провайдера;
- отклонённый provider request;
- несовместимую или неготовую спецификацию;
- пустой пользовательский ввод.

Raw provider body, prompt, system instructions, API-ключ и headers в
пользовательское сообщение и структурные runtime-логи не включаются.

## Диагностика

| Симптом | Что проверить |
| --- | --- |
| «Индекс недоступен или истёк» | Vector Store имеет ограниченный TTL. Повторно создайте RAG-конфигурацию из исходных файлов. |
| «AI Studio отклонил запуск агента» | Проверьте актуальность API-ключа, выбранный folder ID и роль `ai.assistants.admin`. |
| Web Search отклоняется при рабочем one-prompt | Проверьте доступность Web Search и квоту в выбранном каталоге. |
| Timeout | Повторите запрос позднее; test run stateless и не требует восстановления локального состояния. |

UI намеренно не показывает raw provider body. Для диагностики используйте
структурные логи сервиса с `request_id`: они содержат категорию ошибки и
длительность, но не prompt или credentials.

## Проверка

Обычный `pytest` использует fake client и не обращается в облако. Opt-in
credentialed E2E отдельно подтверждает:

- One Prompt;
- Web Search;
- RAG/File Search с временным Vector Store;
- cleanup временных file/vector-store ресурсов;
- отсутствие credentials в runtime export и результате.

Команды приведены в [testing.md](testing.md).

## Ограничения

- один stateless запрос вместо постоянного runtime-чата;
- нет streaming;
- истёкший RAG index не восстанавливается автоматически;
- не создаётся постоянная Agent Atelier entity и не возвращается `agent_id`;
- произвольные function/MCP tools не поддерживаются.

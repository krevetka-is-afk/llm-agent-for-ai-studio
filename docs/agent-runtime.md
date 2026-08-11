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
| `code_interpreter` | `{"type": "code_interpreter", "container": {"type": "auto", "memory_limit": "1g", "network_policy": {"type": "disabled"}}}` |

Внутренние orchestration tools никогда не попадают в runtime. Для File Search
adapter сначала вызывает `vector_stores.retrieve(index_id)` и не отправляет
Responses API запрос, если индекс отсутствует, истёк или не завершён.

Code Interpreter descriptor хранит capability и безопасные defaults, но не
provider state. Базовый runtime никогда не содержит `file_ids`, `container_id`
или пользовательские bytes. IDs входов добавляются в глубокую копию tool config
только после upload текущего preview request.

## Application и UI

`AIInteractionService.test_agent_specification()`:

1. ограничивает тестовый input 10 000 символами;
2. строго восстанавливает и повторно валидирует спецификацию;
3. компилирует тот же базовый config, который доступен для скачивания;
4. для Code Interpreter проверяет локальные inputs и загружает их с
   `purpose=user_data`;
5. добавляет remote input IDs только в request-scoped копию config;
6. создаёт runner через текущую credential boundary и выполняет sync SDK в
   `asyncio.to_thread`;
7. отделяет обычные citations от внутренних `container_file_citation`;
8. потоково сохраняет разрешённые outputs по локальным handles и удаляет
   известные remote files/containers в `finally`;
9. возвращает ответ, citations, usage, `response_id`, локальные generated files
   и типизированные предупреждения cleanup/download.

Метод не принимает `ConversationState` и не изменяет builder-диалог. Файлы
Builder-чата не переиспользуются: inputs каждого stateless preview выбираются
явно. Streamlit хранит preview по fingerprint spec-card и метаданных/content
digest выбранных файлов; изменение спецификации или inputs инвалидирует старый
результат.

Технические поля снабжены tooltip-справкой: отдельно объясняются citations,
input/output/total tokens, `response_id`, runtime config, template и Vector
Store ID. После успешного теста UI предлагает два явно разделённых пути:

1. no-code перенос модели, инструкции, tools и параметров в Agent Atelier;
2. ZIP-пакет для разработчика с обоими JSON, `example.py`, `.env.example` и
   README.

ZIP создаётся в памяти и не содержит API-ключ, folder ID, пользовательские
файлы, generated artifacts или временные file/container/response IDs. Для Code
Interpreter `example.py` показывает полный цикл `--file` → upload → привязка к
копии request → bounded download → cleanup. Ссылки на официальную инструкцию
Agent Atelier доступны как в карточке результата, так и в sidebar.

## Безопасные ошибки

UI различает:

- недоступный или истёкший Vector Store;
- timeout провайдера;
- отклонённый provider request;
- несовместимую или неготовую спецификацию;
- пустой пользовательский ввод.
- недопустимое количество/размер/путь входных файлов;
- ошибку скачивания или превышение лимита generated artifact;
- неполный best-effort cleanup без показа remote IDs.

Raw provider body, prompt, system instructions, API-ключ и headers в
пользовательское сообщение и структурные runtime-логи не включаются.

## Диагностика

| Симптом | Что проверить |
| --- | --- |
| «Индекс недоступен или истёк» | Vector Store имеет ограниченный TTL. Повторно создайте RAG-конфигурацию из исходных файлов. |
| «AI Studio отклонил запуск агента» | Проверьте API-ключ, folder ID, scope `yc.ai.foundationModels.execute` и роли `ai.assistants.editor`/`ai.languageModels.user`. |
| Web Search отклоняется при рабочем one-prompt | Проверьте доступность Web Search и квоту в выбранном каталоге. |
| Code Interpreter не вызывается | Проверьте поддержку tool выбранной моделью; текущий контракт подтверждён для `gpt-oss-120b`. |
| Generated file не появился | Проверьте, что модель создала и процитировала файл, затем типизированное warning-сообщение; HTML/SVG/XML/unknown доступны только как download. |
| Cleanup warning | Удалите ресурс вручную при необходимости; auto-container имеет provider TTL 20 минут, но TTL не заменяет cleanup. |
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
- Code Interpreter с TXT/CSV inputs, `code_interpreter_call`, скачиванием
  `result.csv` и cleanup input/output files, container и response;
- cleanup временных file/vector-store ресурсов;
- отсутствие credentials в runtime export и результате.

Команды приведены в [testing.md](testing.md).

## Ограничения

- один stateless запрос вместо постоянного runtime-чата;
- model response не показывается потоково; generated files скачиваются
  потоково по 64 KiB;
- истёкший RAG index не восстанавливается автоматически;
- не создаётся постоянная Agent Atelier entity и не возвращается `agent_id`;
- Code Interpreter использует только auto-container, 1 GiB и выключенную сеть;
  explicit containers, network allowlist и sandbox secrets не поддерживаются;
- до 5 inputs (10 MiB каждый, 25 MiB суммарно) и до 10 outputs (10 MiB каждый,
  25 MiB суммарно) на preview;
- стоимость, rate limits и доступность tools определяются текущими квотами и
  тарифами Yandex AI Studio; перед production deployment их нужно сверить с
  официальной документацией и партнёрской командой;
- `gpt-oss-120b` прошёл credentialed smoke, но совместимость другой модели с
  Code Interpreter должна подтверждаться отдельным E2E;
- произвольные function/MCP tools не поддерживаются.

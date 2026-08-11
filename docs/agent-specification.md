# AgentSpecification

`AgentSpecification` — формальный артефакт MVP Agent Builder. Он описывает
создаваемого пользователем агента и отделён от runtime-объектов запроса
`InteractionRequest`, `RequestContext` и внутреннего состояния coordinator.

Фактическая модель находится в
`src/ai_studio_agent_builder/domain/specification.py`, каталог шаблонов и
компонентов — в `src/ai_studio_agent_builder/domain/catalog.py`.

## Назначение

Спецификация закрывает требование практики: подготовить, уточнить, проверить и
передать структуру создаваемого интеллектуального агента. Текущий MVP не
создаёт отдельную постоянную remote agent entity в AI Studio; он формирует
переносимое JSON-описание агента, позволяет выполнить его через Responses API
и, для RAG-сценария, создаёт связанный vector index.

## Поля

| Поле | Назначение |
| --- | --- |
| `schema_version` | Версия схемы экспортируемой спецификации. |
| `template` | Выбранный шаблон: `one_prompt` или `rag`. |
| `status` | `draft`, `needs_clarification` или `ready`. |
| `validation.missing_fields` | Полный список обязательных полей, которых не хватает. |
| `validation.issues` | Нарушения совместимости шаблона и компонентов. |
| `purpose` | Назначение создаваемого агента. |
| `audience` | Целевая аудитория или контекст использования. |
| `inputs` | Ожидаемые входы будущего агента. |
| `instructions` | System-level инструкции будущего агента. |
| `constraints` | Ограничения поведения, безопасности, источников и эксплуатации. |
| `knowledge_sources` | Подключённые источники знаний. |
| `tools` | Публичные прикладные инструменты создаваемого агента. |
| `expected_result` | Ожидаемый результат работы создаваемого агента. |
| `parameters` | Template-specific параметры без секретов. |

## Валидация

Валидация детерминирована и возвращает все найденные проблемы за один проход.
Приложение не помечает спецификацию как `ready`, пока обязательные поля или
ошибки совместимости остаются.

Минимальные обязательные поля:

- `one_prompt`: `purpose`, `instructions`, `expected_result`;
- `rag`: `purpose`, `instructions`, `expected_result`, `knowledge_sources`,
  `tools`.

Правила one-prompt с веб-поиском:

- `web_search` является опциональным публичным tool и добавляется только при
  подтверждённой потребности в актуальной информации или поиске в интернете;
- `knowledge_sources` остаётся пустым, поскольку встроенный веб-поиск не требует
  vector index и не является RAG;
- повторное обновление черновика без выбора `web_search` сохраняет прежнее
  значение, а явный отказ удаляет только этот tool;
- переносимый descriptor использует `tool_id: "web_search"` и безопасный параметр
  `search_context_size: "medium"`; при выполнении через Yandex Responses API он
  соответствует built-in tool
  `{"type": "web_search", "search_context_size": "medium"}`.

Дополнительные RAG-правила:

- среди tools должен быть `knowledge_search`;
- должен быть хотя бы один knowledge source;
- `parameters.index_id` должен содержать ID фактически созданного индекса;
- `knowledge_search.parameters.index_id` должен совпадать с
  `parameters.index_id`;
- неизвестные tool-компоненты отклоняются.

Параметры с secret-like ключами (`api_key`, `token`, `secret`, `password`,
`credential`) делают спецификацию неготовой и заменяются на `[REDACTED]` при
JSON-сериализации.

Черновик обновляется через function tool `update_agent_specification`. Готовый
артефакт появляется в результате только после успешного
`finalize_agent_specification`; свободный markdown-текст модели не разбирается
как источник структурированных полей.

## Восстановление и исполнение

Сохранённая запись считается недоверенным вводом. Перед тестовым запуском
`AgentSpecification.from_record()`:

- принимает только schema `1.0` и известные поля;
- проверяет типы вложенных sources, tools и validation issues;
- требует совпадения `agent_type` и `template`;
- повторно вычисляет status/validation и сравнивает их с записью;
- отклоняет неизвестные tools, несовпадающие RAG index IDs и runtime-поля с
  `[REDACTED]`.

После этого pure compiler создаёт отдельный `ExecutableAgentConfig`. Доменный
`knowledge_search` становится нативным Responses API `file_search`, а
`web_search` сохраняется как built-in tool. Runtime model и параметры генерации
берутся из конфигурации приложения, а не из доменной спецификации.

Полный контракт описан в [agent-runtime.md](agent-runtime.md).

## Пример one-prompt-спецификации с Web Search

```json
{
  "schema_version": "1.0",
  "agent_type": "one_prompt",
  "template": "one_prompt",
  "purpose": "Предоставлять пользователю актуальные материалы из интернета",
  "knowledge_sources": [],
  "tools": [
    {
      "tool_id": "web_search",
      "title": "Web search",
      "description": "Searches the public web for current information.",
      "parameters": {
        "search_context_size": "medium"
      }
    }
  ],
  "status": "ready"
}
```

## Пример RAG-спецификации

```json
{
  "schema_version": "1.0",
  "agent_type": "rag",
  "template": "rag",
  "status": "ready",
  "purpose": "Создать RAG-агента по документам онбординга",
  "audience": "Новые сотрудники",
  "inputs": [
    "Сообщение пользователя"
  ],
  "instructions": "Используй подключённый индекс и указывай источник.",
  "constraints": [
    "Векторный индекс автоматически удаляется через 1 день после последней активности."
  ],
  "knowledge_sources": [
    {
      "source_id": "file-1",
      "title": "handbook.pdf",
      "kind": "uploaded_file",
      "reference": "file-1"
    }
  ],
  "tools": [
    {
      "tool_id": "knowledge_search",
      "title": "Knowledge search",
      "description": "Поиск релевантных фрагментов в векторном индексе knowledge.",
      "parameters": {
        "index_id": "index-1",
        "index_name": "knowledge"
      }
    }
  ],
  "expected_result": "Переносимая спецификация RAG-агента, system prompt и идентификатор созданного векторного индекса.",
  "parameters": {
    "index_id": "index-1",
    "index_name": "knowledge",
    "ttl_days": 1
  },
  "validation": {
    "status": "ready",
    "missing_fields": [],
    "issues": []
  }
}
```

## Границы текущей версии

- Draft и последняя готовая спецификация хранятся в состоянии текущего диалога;
  постоянного внешнего хранилища в MVP нет.
- LLM формулирует уточняющие вопросы по `missing_fields`, но статус готовности
  определяется валидатором приложения и function-tool финализацией.
- Произвольные внешние function/MCP tools и marketplace компонентов находятся
  вне MVP; встроенный `web_search` поддерживается явно.
- Тестовый Responses API запуск stateless и не создаёт постоянный `agent_id`.

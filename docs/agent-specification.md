# AgentSpecification

`AgentSpecification` — формальный артефакт MVP Agent Builder. Он описывает
создаваемого пользователем агента и отделён от runtime-объектов запроса
`InteractionRequest`, `RequestContext` и внутреннего состояния coordinator.

Фактическая модель находится в `src/agent_specification.py`, каталог шаблонов и
компонентов — в `src/component_catalog.py`.

## Назначение

Спецификация закрывает требование практики: подготовить, уточнить, проверить и
передать структуру создаваемого интеллектуального агента. Текущий MVP не
создаёт отдельную постоянную remote agent entity в AI Studio; он формирует
переносимое JSON-описание агента и, для RAG-сценария, создаёт связанный vector
index.

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

Дополнительные RAG-правила:

- среди tools должен быть `knowledge_search`;
- должен быть хотя бы один knowledge source;
- `parameters.index_id` должен содержать ID фактически созданного индекса;
- неизвестные tool-компоненты отклоняются.

Параметры с secret-like ключами (`api_key`, `token`, `secret`, `password`,
`credential`) делают спецификацию неготовой и заменяются на `[REDACTED]` при
JSON-сериализации.

Черновик обновляется через function tool `update_agent_specification`. Готовый
артефакт появляется в результате только после успешного
`finalize_agent_specification`; свободный markdown-текст модели не разбирается
как источник структурированных полей.

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
- Произвольные внешние tools и marketplace компонентов находятся вне MVP.

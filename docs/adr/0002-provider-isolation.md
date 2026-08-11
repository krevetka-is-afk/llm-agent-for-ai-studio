# ADR-0002: Изоляция Yandex/OpenAI provider contracts

- Статус: Accepted
- Дата: 2026-08-11

## Контекст

Responses, Files и Vector Store APIs возвращают SDK-specific объекты и ошибки.
Если они распространяются в application/UI, provider changes начинают менять
все слои, а raw errors могут раскрыть чувствительные данные.

## Решение

Конкретные Yandex/OpenAI API clients, model URI, provider requests, Responses
API parsing и exception mapping находятся только в
`infrastructure/yandex_ai_studio`. Application работает через ports и получает
внутренние immutable DTO:

- preview text/usage/citations;
- remote input/output references;
- safe error taxonomy;
- normalized resource status.

Runtime compiler остаётся provider-neutral настолько, насколько это позволяет
текущий продуктовый контракт. Request-scoped binding provider IDs выполняется
на application/infrastructure boundary и не изменяет базовый экспортируемый
runtime.

OpenAI Agents SDK, используемый для самого Builder, является отдельной adapter
границей. Импорты его event types разрешены только в `builder/agents/`. Модуль
`sdk_event_adapter.py` преобразует raw run events в собственные normalized
builder events; `builder/result_assembly.py` не импортирует SDK и не получает
raw event objects.

## Альтернативы

- Передавать SDK objects до UI: меньше mapping кода, но сильная связность и риск
  утечек — отклонено.
- Создать универсальный multi-cloud abstraction: преждевременно, так как второй
  provider не выбран — отклонено.
- Узкие ports по текущим use cases: выбрано.

## Последствия

- Provider adapter содержит явный mapping code и fixture tests.
- Domain/application tests не требуют SDK response objects.
- Добавление второго provider возможно, но не является целью `v0.1.0`.
- Raw provider error логируется только в redacted infrastructure context;
  пользователю возвращается safe taxonomy.

## Контроль

- architecture test разрешает API SDK imports только в infrastructure, а
  Agents SDK event imports — только в `builder/agents`;
- adapter tests проверяют dict- и object-shaped fixtures;
- exported spec/runtime/log tests запрещают credentials и transient IDs.

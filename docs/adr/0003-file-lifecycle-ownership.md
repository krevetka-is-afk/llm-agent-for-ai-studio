# ADR-0003: Application владеет жизненным циклом файлов preview

- Статус: Accepted
- Дата: 2026-08-11

## Контекст

Code Interpreter требует загрузки входных файлов, request-scoped binding,
скачивания outputs и cleanup на success/failure. Если upload, download и delete
распределены между UI, runner и provider helpers, partial failure оставляет
remote resources и partial local files без владельца.

## Решение

Application layer владеет registry всех локальных и remote artifacts одного
preview request. Для CI-3 это реализует `PreviewInputFileLifecycle`; локальным
conversation retention отдельно владеет `ConversationFileService`. Input
lifecycle:

1. валидирует trusted local handles и квоты;
2. регистрирует remote reference сразу после create;
3. формирует только request-scoped binding;
4. скачивает output chunked с per-file/total caps;
5. удаляет partial local output;
6. выполняет cleanup всех известных remote resources в `finally`.

CI-4 реализует `PreviewOutputFileLifecycle` под тем же ownership-контрактом:
runner возвращает typed remote references, application выполняет bounded
streaming download и cleanup, UI получает только local handles.

Infrastructure `FileResourceGateway` реализует атомарные provider operations.
Runner только возвращает artifact references. UI отображает local artifact DTO
и не знает remote IDs.

## Альтернативы

- Cleanup в UI: не покрывает disconnect/process errors — отклонено.
- Cleanup внутри runner: смешивает model execution с local storage и download —
  отклонено.
- Полагаться только на provider TTL: не освобождает квоты своевременно и не
  даёт наблюдаемого outcome — отклонено.

## Последствия

- Application use case становится длиннее, но resource ownership однозначен.
- Cleanup error не отменяет уже полученный успешный пользовательский результат;
  он создаёт bounded warning/metric.
- Локальный retention и remote cleanup конфигурируются отдельно.
- Stateful explicit containers остаются вне `v0.1.0`.

## Контроль

- tests для partial upload, validation/binding failure, timeout, provider error,
  oversized/stream error и success;
- отсутствие file/container IDs в spec, base runtime, UI и логах;
- E2E удаляет все известные input/output resources в `finally`;
- file lifecycle matrix поддерживается в
  `docs/architecture/file-data-lifecycle.md`.

# ADR-0004: Контракт Yandex Code Interpreter проверяется credentialed E2E

- Статус: Accepted
- Дата: 2026-08-11

## Контекст

Domain-спецификация должна оставаться переносимой, а provider adapter — точно
формировать request и разбирать ссылки на созданные файлы. Одних типов OpenAI
SDK для этого недостаточно: поддержка tool конкретной моделью, режим выполнения
Responses API и фактическая форма ответа являются внешним контрактом Yandex AI
Studio.

Официальная документация задаёт:

- tool `code_interpreter` с auto-container и опциональными `file_ids`;
- memory tiers `1g`, `4g`, `16g`, `64g` и network policy;
- передачу файлов через Files API с `purpose=user_data`;
- созданные файлы в аннотациях `container_file_citation`;
- auto-container с временем жизни 20 минут после последней активности;
- роли сервисного аккаунта `ai.assistants.editor` и
  `ai.languageModels.user`, а также API-key scope
  `yc.ai.foundationModels.execute` для опубликованного примера.

Источники:

- [Выполнить задачу с помощью Code Interpreter](https://aistudio.yandex.ru/docs/ru/ai-studio/operations/agents/use-code-interpreter.html);
- [Code Interpreter](https://aistudio.yandex.ru/docs/ru/ai-studio/concepts/agents/tools/code-interpreter.html);
- [Доступные генеративные модели](https://aistudio.yandex.ru/docs/ru/ai-studio/concepts/generation/models.html).

## Проверенный контракт

11 августа 2026 года выполнен credentialed smoke на:

- `openai==2.38.0`, разрешённом текущим ограничением `openai>=2.32.0`;
- Responses API `https://ai.api.cloud.yandex.net/v1`;
- модели `gpt-oss-120b` из `generated_agent_runtime`;
- двух входах: TXT и CSV;
- `container.type=auto`, `memory_limit=1g`, network disabled.

Минимальная форма запроса:

```json
{
  "model": "gpt://<folder_id>/gpt-oss-120b",
  "input": "<user prompt>",
  "tools": [
    {
      "type": "code_interpreter",
      "container": {
        "type": "auto",
        "file_ids": ["<trusted_file_id_1>", "<trusted_file_id_2>"],
        "memory_limit": "1g",
        "network_policy": {"type": "disabled"}
      }
    }
  ]
}
```

Smoke подтвердил:

1. `gpt-oss-120b` вызывает Code Interpreter и читает оба входа;
2. stream содержит события `response.code_interpreter_call.*`;
3. финальный response содержит один или несколько
   `code_interpreter_call` с `container_id`, `code`, `status` и `outputs`;
4. созданный `result.csv` появляется в `message.content[].annotations[]` как
   `container_file_citation` с полями `container_id`, `file_id`, `filename`,
   `start_index`, `end_index`;
5. `client.files.content(file_id)` возвращает содержимое созданного файла;
6. input/output files, auto-container и response принимают явный delete.

Обезличенная фактическая форма хранится в
`tests/fixtures/code_interpreter/yandex_response_contract.json`. Количество
reasoning/tool-call элементов не является стабильной частью контракта.

## Решение

1. Сохраняем `gpt-oss-120b` как текущую generated-runtime модель: tool
   подтверждён smoke-тестом. Qwen с большим контекстом остаётся рекомендуемым
   override для контекстно-нагруженных задач, но миграция модели не нужна для
   первой реализации.
2. `AgentSpecification` хранит только capability и безопасные defaults. Ни
   `file_ids`, ни `container_id` не сериализуются.
3. Application lifecycle загружает локальные inputs и внедряет полученные IDs
   в копию runtime config непосредственно перед request.
4. Provider runner нормализует `container_file_citation` в отдельный artifact
   reference. Он не скачивает bytes и не пишет локальные файлы.
5. Первая версия использует только auto-container, `memory_limit=1g` и
   `network_policy=disabled`. Explicit container, allowlist и secrets не входят
   в контракт `v0.1.0`.
6. Credentialed E2E использует streaming плюс retrieve/poll, как официальный
   пример. Production adapter обязан корректно принимать как уже завершённый,
   так и незавершённый initial response; выбор sync/stream остаётся деталью
   infrastructure.
7. Provider TTL не заменяет cleanup в `finally`.

## Альтернативы

- Считать совместимость OpenAI SDK доказательством совместимости API —
  отклонено: typed request не подтверждает поддержку модели и форму ответа.
- Сразу заменить `gpt-oss-120b` на Qwen — отклонено: текущая модель прошла
  credentialed smoke, а смена модели меняет поведение runtime.
- Хранить реальные response/file/container IDs в fixture — отклонено: они не
  нужны для контракта и создают утечку provider metadata.
- Использовать explicit container в preview — отклонено: он требует stateful
  ownership, не соответствующий текущему stateless flow.

## Контроль

- обычный test suite проверяет обезличенную fixture и отсутствие raw IDs;
- opt-in E2E загружает TXT/CSV, проверяет вычисление и скачивает `result.csv`;
- E2E удаляет все известные input/output files, container и response в
  `finally`;
- CI-3 и CI-4 должны использовать эту fixture для parser/binding tests;
- минимальные роли и scope нужно сверять с актуальной документацией Yandex AI
  Studio перед релизом.

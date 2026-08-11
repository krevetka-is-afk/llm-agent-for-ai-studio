# Тестирование

## Локальный quality gate

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
uv build --wheel --sdist
uv run pre-commit run --all-files
```

Тесты фиксируют runtime entrypoints, Docker/Compose contract, единственное
package-дерево, transactional conversation state, явные routing overrides и различие
между web search и vector RAG, добавление/сохранение/удаление публичного
`web_search` в one-prompt-спецификации, передачу `max_turns`, Telegram
serialization/secret TTL, UI helpers, tooltip contracts, developer ZIP без
секретов и отсутствие API-ключа в tool context. RAG-регрессии отдельно
проверяют сохранение доверенных файлов между сообщениями, отсутствие `file_id`
в tool schema, идемпотентное повторное создание и отбрасывание ошибочного
tool-output вместо отображения его как ID индекса.

## Credentialed Yandex AI Studio E2E

E2E opt-in состоит из двух наборов:

- builder RAG создаёт индекс и проверяет типизированный результат диалога;
- generated-agent runtime выполняет One Prompt, Web Search и RAG/File Search
  через Responses API, проверяет отсутствие credentials в runtime/result и
  удаляет временные file/vector-store ресурсы в `finally`.

```bash
cp .env.e2e.example .env.e2e
uv run --env-file .env.e2e pytest \
  -m yandex_ai_studio_e2e tests/e2e/test_yandex_ai_studio_rag_e2e.py

uv run --env-file .env.e2e pytest \
  -m yandex_ai_studio_e2e \
  tests/e2e/test_yandex_ai_studio_agent_runtime_e2e.py
```

Задайте `RUN_YANDEX_AI_STUDIO_E2E=1`, `YC_AI_STUDIO_API_KEY` и
`YC_AI_STUDIO_FOLDER_ID`. Используйте отдельный короткоживущий ключ с минимальной
ролью `ai.assistants.admin`. `YC_AI_STUDIO_E2E_KEEP_REMOTE=1` допустим только для
отладки: оставшиеся ресурсы могут расходовать квоту до ручного удаления или TTL.

Web Search дополнительно помечен
`yandex_ai_studio_web_search_e2e`, потому что зависит от доступной квоты. Перед
признанием generated-agent runtime готовым этот сценарий должен быть выполнен,
а не только снят обычным `pytest`.

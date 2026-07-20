# Тестирование

## Локальный quality gate

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
uv run pre-commit run --all-files
```

Тесты фиксируют runtime entrypoints, Docker/Compose contract, compatibility
imports, transactional conversation state, Telegram serialization/secret TTL,
UI helpers и отсутствие API-ключа в tool context.

## Credentialed Yandex AI Studio E2E

E2E opt-in: он загружает небольшой synthetic file, создаёт однодневный vector
store, проверяет типизированный результат и выполняет best-effort cleanup.

```bash
cp .env.e2e.example .env.e2e
PYTHONPATH=src uv run --env-file .env.e2e pytest \
  -m yandex_ai_studio_e2e tests/e2e/test_yandex_ai_studio_rag_e2e.py
```

Задайте `RUN_YANDEX_AI_STUDIO_E2E=1`, `YC_AI_STUDIO_API_KEY` и
`YC_AI_STUDIO_FOLDER_ID`. Используйте отдельный короткоживущий ключ с минимальной
ролью `ai.assistants.admin`. `YC_AI_STUDIO_E2E_KEEP_REMOTE=1` допустим только для
отладки: оставшиеся ресурсы могут расходовать квоту до ручного удаления или TTL.

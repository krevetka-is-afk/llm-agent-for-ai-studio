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

Release gate дополнительно повторяет проверку production lock и Compose:

```bash
uv export --frozen --no-dev --no-hashes --format requirements-txt \
  --output-file /tmp/agent-builder-requirements.txt
uvx --from pip-audit==2.9.0 pip-audit \
  --requirement /tmp/agent-builder-requirements.txt \
  --no-deps --disable-pip --desc off
docker compose config --quiet
```

Lock не должен содержать известные уязвимости. Минимальные прямые версии
`aiohttp>=3.14.3` и `cryptography>=50.0.0` фиксируют исправленные security
границы; транзитивные зависимости контролируются committed `uv.lock` и audit в
обычном CI.

Тесты проверяют entrypoints, Docker/Compose, границы package, транзакционное
состояние диалога, routing, Web Search, Telegram, UI и экспорт без секретов.
Регрессии Code Interpreter покрывают привязку файлов к запросу, cleanup после
частичного upload, скачивание с лимитами, MIME policy, cache fingerprint и
developer example. RAG-регрессии проверяют сохранение доверенных файлов,
отсутствие `file_id` в tool schema и повторное использование созданного индекса.

## Credentialed Yandex AI Studio E2E

E2E opt-in состоит из трёх наборов:

- builder RAG создаёт индекс и проверяет типизированный результат диалога;
- generated-agent runtime выполняет One Prompt, Web Search, RAG/File Search и
  Code Interpreter через application service. Последний сценарий сохраняет
  inputs через обычный attachment store, проверяет request-scoped binding,
  читает локальный `result.csv`, отсутствие remote IDs в result и фактические
  вызовы удаления input/output files и container;
- UI-регрессия проверяет, что файл Builder-чата восстанавливается после
  промежуточных сообщений и попадает в Code Interpreter preview без повторной
  загрузки пользователем;
- provider-contract smoke загружает TXT и CSV в auto-container, проверяет
  `code_interpreter_call`, скачивает созданный `result.csv` по
  `container_file_citation` и удаляет input/output files, container и response.

Обычный suite использует обезличенную provider fixture и fake clients. Он
проверяет control flow и отсутствие секретов/remote IDs, но не доказывает
доступность tool, модели, квоты или текущую форму ответа Yandex; для этого
обязателен opt-in smoke ниже.

```bash
cp .env.e2e.example .env.e2e
uv run --env-file .env.e2e pytest \
  -m yandex_ai_studio_e2e tests/e2e/test_yandex_ai_studio_rag_e2e.py

uv run --env-file .env.e2e pytest \
  -m yandex_ai_studio_e2e \
  tests/e2e/test_yandex_ai_studio_agent_runtime_e2e.py

uv run --env-file .env.e2e pytest \
  -m yandex_ai_studio_e2e \
  tests/e2e/test_yandex_ai_studio_code_interpreter_contract_e2e.py
```

Для одного core release-gate без quota-sensitive Web Search:

```bash
uv run --env-file .env.e2e pytest -q \
  -m "yandex_ai_studio_e2e and not yandex_ai_studio_web_search_e2e" \
  tests/e2e
```

Задайте `RUN_YANDEX_AI_STUDIO_E2E=1`, `YC_AI_STUDIO_API_KEY` и
`YC_AI_STUDIO_FOLDER_ID`. Используйте отдельный короткоживущий ключ с минимальной
областью `yc.ai.foundationModels.execute` и сервисный аккаунт с ролями
`ai.assistants.editor` и `ai.languageModels.user`; перед запуском сверяйте роли
с актуальной документацией Yandex AI Studio.
`YC_AI_STUDIO_E2E_KEEP_REMOTE=1` допустим только для отладки: оставшиеся ресурсы
могут расходовать квоту до ручного удаления или TTL.

Web Search дополнительно помечен
`yandex_ai_studio_web_search_e2e`, потому что зависит от доступной квоты. Перед
признанием generated-agent runtime готовым этот сценарий должен быть выполнен,
а не только снят обычным `pytest`.

В GitHub Actions credentialed suite доступен только через ручной workflow
`Yandex AI Studio E2E`. Репозиторий должен иметь защищённое environment
`yandex-ai-studio-e2e` с required reviewers и secrets
`YC_AI_STUDIO_API_KEY`/`YC_AI_STUDIO_FOLDER_ID`. Workflow не подписан на
`pull_request`, всегда задаёт `YC_AI_STUDIO_E2E_KEEP_REMOTE=0` и запускает Web
Search только при явном input `include_web_search=true`. Перед тегом `v0.1.0`
core и Web Search jobs должны пройти успешно. Для внешних fork PR эти jobs не
делаются обязательными, потому что им недоступны secrets.

## Последний полный E2E

19 августа 2026 года полный credentialed suite выполнен локально одноразовым
override safety-флага без изменения `.env.e2e`:

```bash
RUN_YANDEX_AI_STUDIO_E2E=1 uv run --env-file .env.e2e \
  pytest -q -x -m yandex_ai_studio_e2e tests/e2e
```

Результат: `6 passed in 73.10s`. Пройдены builder RAG, generated One Prompt,
quota-sensitive Web Search, generated RAG/File Search, service-backed Code
Interpreter и отдельный provider-contract smoke. Service-backed сценарий
подтвердил локальный `result.csv`, отсутствие credentials/remote IDs в public
result и фактический cleanup известных input/output files и auto-container.
Cleanup warnings отсутствовали; значения credentials и provider IDs в протокол
не записывались.

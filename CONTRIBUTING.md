# Как внести вклад

Спасибо за интерес к проекту. Мы приветствуем исправления ошибок, улучшения
документации, тесты и небольшие, хорошо обоснованные изменения продукта.

## До начала работы

1. Проверьте существующие issues и pull requests, чтобы не дублировать работу.
2. Для заметного изменения сначала создайте issue с пользовательским сценарием,
   границами задачи и ожидаемым результатом.
3. Для изменений архитектурных границ, публичных контрактов или жизненного
   цикла внешних ресурсов предложите ADR в `docs/adr/`.
4. Не прикладывайте API-ключи, folder ID, пользовательские файлы, логи с
   секретами или другие персональные данные.

## Локальная разработка

Требуются Python 3.13 и `uv`.

```bash
uv sync --frozen
uv run pre-commit install
```

Запуск Web UI:

```bash
cp .env.web.example .env.web
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode("ascii"))'
uv run --env-file .env.web streamlit run src/ai_studio_agent_builder/entrypoints/web.py
```

Сгенерированный ключ необходимо записать в локальный `.env.web`. Этот файл и
данные из `.local/` не должны попадать в Git.

## Архитектурные правила

- `domain` не зависит от SDK, UI и persistence.
- `application` владеет use cases, портами и контрактами ошибок.
- внешние API, файловая система и базы данных остаются в `infrastructure`.
- `presentation` преобразует ввод и вывод, но не владеет бизнес-правилами.
- composition root связывает реализации; скрытые глобальные зависимости не
  добавляются.
- временные файлы и provider resources должны иметь явного владельца,
  ограниченный срок жизни и best-effort cleanup.

Подробнее: [архитектура](docs/architecture.md) и
[ADR](docs/adr/0001-package-boundaries.md).

## Проверки

Перед pull request выполните:

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
uv build --wheel --sdist
uv run pre-commit run --all-files
```

Credentialed E2E выполняются только при изменении интеграции с Yandex AI Studio
и только с отдельными краткоживущими credentials. Инструкции находятся в
[docs/testing.md](docs/testing.md). Никогда не добавляйте credentials в fixtures
или вывод тестов.

## Коммиты и pull requests

- Делайте один логический шаг на коммит и пишите intent-first сообщение.
- Не смешивайте рефакторинг с изменением поведения без необходимости.
- Добавляйте или обновляйте тесты для изменённого поведения.
- Опишите риск, способ проверки и известные ограничения в pull request.
- Обновите документацию, если меняется публичный контракт или сценарий.

Отправляя вклад, вы подтверждаете право передать его проекту под лицензией MIT,
указанной в [LICENSE](LICENSE).

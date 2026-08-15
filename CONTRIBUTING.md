# Как внести вклад

Исправления, тесты и улучшения документации можно отправлять через pull request.
Для заметной новой функции сначала создайте issue и опишите пользовательский
сценарий.

Не добавляйте в issue, логи или fixtures API-ключи, folder ID, пользовательские
файлы и персональные данные.

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

Запишите сгенерированный ключ в `.env.web`. Этот файл и каталог `.local/` не
должны попадать в Git.

## Границы модулей

- `domain` не зависит от SDK, UI и persistence;
- `application` содержит сценарии, порты и ошибки;
- внешние API, файловая система и базы данных находятся в `infrastructure`;
- `presentation` преобразует ввод и вывод, не добавляя бизнес-правил;
- composition root связывает реализации;
- у временных файлов и provider-ресурсов должны быть владелец, срок жизни и
  cleanup.

Подробнее: [архитектура](docs/architecture.md) и
[ADR](docs/adr/0001-package-boundaries.md).

## Проверки

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
uv build --wheel --sdist
uv run pre-commit run --all-files
```

Credentialed E2E нужны при изменении интеграции с Yandex AI Studio. Используйте
отдельный короткоживущий ключ и инструкции из [docs/testing.md](docs/testing.md).

## Pull request

- Один логический шаг — один коммит.
- Изменение поведения сопровождается тестом.
- Рефакторинг не смешивается с новой функцией.
- В описании PR укажите риск и выполненные проверки.
- При изменении публичного сценария обновите документацию.

Вклад принимается по лицензии MIT из [LICENSE](LICENSE).

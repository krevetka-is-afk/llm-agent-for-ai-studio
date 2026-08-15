# Чек-лист релиза

## Код и CI

- [x] Локально проходят Ruff, `ty`, `pytest`, сборка пакета и pre-commit hooks.
- [x] Credentialed E2E покрывает RAG и Code Interpreter.
- [x] CI проверяет код, зависимости и новые коммиты на секреты.
- [ ] Изменения прошли review и объединены в `main`.
- [ ] CI зелёный на финальном commit в `main`.
- [ ] Full-history secret scan запущен вручную на финальном `main`.
- [ ] Web UI, ссылки и developer ZIP проверены из чистого clone.

## Настройки GitHub

- [ ] Для `main` включены pull request review и обязательные CI checks.
- [ ] Force push и удаление `main` запрещены.
- [ ] Создан environment `yandex-ai-studio-e2e` с reviewers, ограничением веток
  и secrets `YC_AI_STUDIO_API_KEY` и `YC_AI_STUDIO_FOLDER_ID`.
- [ ] Включены Dependabot alerts и security updates.
- [ ] Включены secret scanning, push protection и CodeQL.
- [ ] Настроен Private vulnerability reporting.
- [ ] Заполнены описание, topics, homepage и social preview репозитория.

## Тег и GitHub Release

- [ ] `CHANGELOG.md` содержит дату и номер версии вместо `Unreleased`.
- [ ] Версия пакета совпадает с тегом.
- [ ] Wheel и sdist собраны из чистого clone и проверены на локальные файлы.
- [ ] Для артефактов опубликованы checksums.
- [ ] Созданы аннотированный тег `v0.1.0` и GitHub Release.

## После публикации

- [ ] Проверены issue forms, pull request template и приватный security report.
- [ ] Yandex AI Studio E2E запущен из default branch без оставшихся ресурсов.
- [ ] Назначены ответственные за triage и обновление зависимостей.

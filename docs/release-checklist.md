# Чек-лист публичного релиза

Публикация разрешена только после закрытия всех блокирующих пунктов. Локальная
готовность не заменяет согласование бренда, прав и внешних настроек GitHub.
Последний технический снимок и принятые риски зафиксированы в
[`release-readiness.md`](release-readiness.md).

## 1. Идентичность и права — блокирует публикацию

- [ ] Подтверждены GitHub owner и окончательное имя репозитория.
- [ ] Подтверждено право использовать бренд Shada в open-source проекте.
- [ ] Yandex письменно согласовал точную формулировку партнёрства и правила
  визуальной атрибуции.
- [ ] Проверены права на весь код, документацию, примеры и тестовые данные в
  публикуемой истории.
- [ ] Подтверждены copyright notice в `LICENSE` и необходимость списка авторов.
- [ ] README, описание репозитория и release notes используют один утверждённый
  текст из `docs/branding.md`.

## 2. Безопасность — блокирует публикацию

- [x] Реальные `.env`, credentials, локальные базы и пользовательские файлы
  исключены из Git.
- [x] CI настроен на gitleaks-скан каждого push/PR, а ручной release workflow —
  на скан всей достижимой истории.
- [x] Production lock проверяется `pip-audit`; на 2026-08-11 известных
  уязвимостей не найдено.
- [x] Credentialed E2E запускается только вручную и не запускается автоматически
  из внешнего pull request.
- [ ] Создан и защищён GitHub Environment `yandex-ai-studio-e2e`; credentials
  сохранены как environment secrets, назначены reviewers и deployment branches.
- [x] Локальный Gitleaks `v8.30.1` проверил всю достижимую историю во всех refs;
  четыре совпадения с тестовым `ApiKey123456` классифицированы и ограничены
  точными fingerprints в `.gitleaksignore`, повторный scan не нашёл утечек.
- [x] Sdist ограничен installable package allowlist; fresh artifact и Docker
  build context не включают локальные отчёты, credentials, outputs и `dist/`.
- [x] Upload/storage lifecycle закрывает metadata/stream size limits, traversal,
  partial provider cleanup, TTL fallback и минимальные POSIX-права.
- [ ] Ручной full-history workflow запущен на финальном `main`, результат
  сохранён в GitHub Actions.
- [ ] Если секрет когда-либо попадал в историю, он отозван, история очищена, а
  повторный full-history scan успешен.
- [ ] После переключения visibility включён **Private vulnerability reporting**.
- [ ] Включены Dependabot alerts и security updates.
- [ ] Включены GitHub secret scanning, push protection и CodeQL default setup.

## 3. Репозиторий и review — блокирует публикацию

- [x] Добавлены `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`,
  `SUPPORT.md`, `GOVERNANCE.md`, issue forms и pull request template.
- [x] Настроены Dependabot version updates для `uv`, GitHub Actions,
  pre-commit и Docker.
- [ ] Все изменения объединены в `main` через review; CI зелёный на merge SHA.
- [ ] Для `main` включены required pull request и required CI checks; force push
  и удаление ветки запрещены.
- [ ] Настроены описание, topics, homepage и social preview репозитория.
- [ ] Проверены ссылки GitHub в `pyproject.toml`, issue forms и документации;
  при изменении owner/name они обновлены до публикации.
- [ ] Принято решение о GitHub Discussions и назначены maintainers/moderators.

## 4. Качество релиза — блокирует тег

- [x] Локальный quality gate прошёл: format, lint, typecheck, tests, build,
  pre-commit и Compose validation.
- [x] 2026-08-11 credentialed E2E прошёл: 6 сценариев, включая service-backed
  Code Interpreter upload/run/download/cleanup.
- [ ] Повторён полный quality gate на финальном release commit.
- [ ] Версия и секция `CHANGELOG.md` переведены из `Unreleased` в датированный
  релиз.
- [ ] Из чистого clone проверены Web UI, developer bundle и ссылки README.
- [ ] Создан аннотированный тег `v0.1.0` и GitHub Release с проверенными
  artifacts и checksums.

## 5. После публикации

- [ ] Проверены issue forms, pull request template и кнопка приватного отчёта об
  уязвимости от пользователя без прав maintainer.
- [ ] Ручной workflow Yandex AI Studio E2E запущен из default branch и завершён
  без утечки секретов или оставшихся provider resources.
- [ ] Опубликованы согласованные анонсы и ссылка на репозиторий.
- [ ] Назначен владелец triage и определён ритм dependency/security review.

# Отчёт о готовности к публичному релизу

- Дата проверки: 2026-08-11
- Ветка: `codex/system-design-code-interpreter`
- Целевой релиз: `0.1.0`
- Итог: **не открывать visibility до закрытия внешних блокеров**

Локальный код, supply chain и release artifacts прошли технический gate. Сам
репозиторий остаётся приватным, а юридическая атрибуция ШАД/Yandex и
обязательные GitHub controls ещё не подтверждены. Публичная публикация в рамках
этой проверки не выполнялась.

## Подтверждённые результаты

| Область | Результат | Доказательство |
| --- | --- | --- |
| Format/lint/types | Pass | Ruff format, Ruff lint и `ty check` |
| Unit/integration | Pass | `284 passed, 6 skipped` |
| Credentialed provider regression | Pass | RAG `1 passed`; service-backed Code Interpreter `1 passed` после изменения TTL contract |
| Полный credentialed E2E | Pass | Ранее на этой ветке: 6 сценариев за 58.71 s |
| Git history secrets | Pass | Gitleaks v8.30.1: все достижимые local refs, leaks не найдены |
| Dependency vulnerabilities | Pass | `pip-audit` для production lock: известных уязвимостей не найдено |
| Static security scan | Pass | Bandit 1.8.6 на Python 3.13; findings не найдены |
| Distribution | Pass | Fresh wheel 123 KB, sdist 87 KB; local reports, env, outputs и PII paths отсутствуют |
| Docker | Pass | Compose validation и `docker buildx build --check`; warnings отсутствуют |
| Hooks | Pass | Все pre-commit hooks |
| Documentation links | Pass | Broken local Markdown links: 0 |

Bandit 1.8.6 нельзя запускать здесь через системный Python 3.14: инструмент
падает внутри собственного AST plugin из-за удалённого `ast.Num`. Проверенный
воспроизводимый запуск закреплён на поддерживаемом проектом Python 3.13.

## Закрытые security/release findings

- Sdist имеет явный package allowlist. Старый 5.6 MB artifact с локальными
  отчётами заменён fresh 87 KB сборкой; `dist/` также исключён из Docker context.
- Telegram проверяет declared size до download, потоково считает фактические
  bytes, удаляет partial file и ограничивает глобальную concurrency процесса.
- User storage scopes запрещают absolute/traversal/symlink escape. Накопление
  файлов ограничено per-user и global quotas.
- API-key и conversation SQLite databases получают POSIX mode `0600`, upload
  directories — `0700`; забытые Web API-key rows удаляются через 30 дней.
- OAuth prototype слушает loopback по умолчанию и разрешает исходящие auth/token
  запросы только к HTTPS endpoints из Yandex allowlist.
- Stateful RAG удаляет files/vector store при ошибке build. Defense-in-depth TTL
  ограничивает provider input files 48 часами, vector store — одним днём.
- Full-history secret scan вынесен в отдельный ручной release workflow; обычный
  CI проверяет предлагаемый commit range.

## Принятые ограниченные риски

- Provider cleanup остаётся best effort: при сетевой ошибке ресурс может жить до
  TTL. Для `0.1.0` срок ограничен 48 часами для files и одним днём для vector
  stores. Отдельный persistent janitor не реализован.
- Локальная storage quota и Telegram concurrency относятся к одному процессу.
  Горизонтальный deployment требует общей quota/rate-limit инфраструктуры и не
  входит в поддерживаемую single-instance конфигурацию `0.1.0`.
- Telegram и OAuth остаются экспериментальными адаптерами и не запускаются по
  умолчанию.

## Внешние блокеры публикации

Снимок GitHub `krevetka-is-afk/llm-agent-for-ai-studio` на дату проверки:

- visibility — `PRIVATE`;
- default branch — `main`, branch protection отсутствует или недоступен;
- GitHub Environments — 0, поэтому `yandex-ai-studio-e2e` ещё не создан;
- Dependabot alerts выключены или недоступны;
- topics и homepage не настроены, Discussions выключены;
- описание репозитория ещё использует старую формулировку;
- ручной full-history workflow ещё не запускался на финальном merge SHA.

До изменения visibility обязательны:

1. подтвердить owner/final repository name и права на публикуемую Git-историю;
2. получить письменное согласование точной формулировки партнёрства и
   использования брендов ШАД/Yandex;
3. объединить изменения в `main` через review и получить зелёный CI на merge
   SHA;
4. включить branch protection, Dependabot/security controls и private
   vulnerability reporting;
5. создать защищённый environment `yandex-ai-studio-e2e`, перенести secrets и
   запустить ручные release/E2E workflows;
6. повторить сборку из clean clone, проверить checksums и только после этого
   создать tag/release и переключить visibility.

Полный операционный список: [release-checklist.md](release-checklist.md).

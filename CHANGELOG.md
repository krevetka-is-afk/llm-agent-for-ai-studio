# История изменений

Значимые изменения проекта фиксируются в этом файле. Формат основан на
[Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии следуют
[Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

### Добавлено

- Web UI для проектирования one-prompt и RAG-приложений в Yandex AI Studio.
- Валидируемый контракт `AgentSpecification` и переносимый runtime config.
- Stateless preview через Responses API с `web_search` и `file_search`.
- Code Interpreter с явным выбором входных файлов, изолированным lifecycle,
  потоковым скачиванием артефактов и best-effort cleanup provider resources.
- Импорт спецификаций и developer ZIP с безопасным исполняемым примером.
- Архитектурные ADR, тестовый контур, opt-in credentialed E2E и supply-chain
  audit.

### Безопасность

- API-ключи хранятся локально в зашифрованном виде и не передаются в model/tool
  context.
- Входные и выходные файлы ограничены политиками размера и количества; remote
  IDs и пользовательские bytes не попадают в экспорт.
- Telegram-загрузки проверяются до скачивания и потоково ограничиваются по
  фактическому числу bytes; storage scopes изолированы от path traversal.
- Временные provider inputs получают 48-часовой TTL, неудачные RAG-запуски
  очищают уже созданные files/vector stores, а локальные sensitive stores
  используют минимальные POSIX-права и bounded retention.
- CI сканирует каждый предлагаемый диапазон commit'ов на секреты, отдельный
  release workflow проверяет всю Git-историю, а production lock проверяется на
  известные уязвимости.

[Unreleased]: https://github.com/krevetka-is-afk/llm-agent-for-ai-studio/commits/main

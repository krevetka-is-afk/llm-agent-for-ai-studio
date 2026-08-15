# История изменений

Формат основан на
[Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии следуют
[Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

### Добавлено

- Web UI для one-prompt и RAG-агентов в Yandex AI Studio.
- Контракт `AgentSpecification` и переносимый runtime config.
- Preview через Responses API с `web_search` и `file_search`.
- Code Interpreter с выбором входных файлов и скачиванием результатов.
- Импорт спецификаций и ZIP с готовым примером запуска.
- ADR, автоматические тесты и отдельный credentialed E2E.

### Безопасность

- API-ключи хранятся локально в зашифрованном виде и не передаются модели.
- Для файлов действуют лимиты размера и количества; содержимое и remote IDs не
  попадают в экспорт.
- Telegram-загрузки проверяются до скачивания и при потоковой записи.
- Временные ресурсы имеют TTL и удаляются после ошибок, когда API доступен.
- CI ищет секреты и известные уязвимости зависимостей.

[Unreleased]: https://github.com/krevetka-is-afk/llm-agent-for-ai-studio/commits/main

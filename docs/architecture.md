# Архитектура

Production-код находится в installable package `ai_studio_agent_builder`.
Приложение разделено на доменную модель, сценарии, Builder, адаптеры и UI.

Дополнительные схемы:

- [System context](architecture/system-context.md)
- [Container view](architecture/container-view.md)
- [Основные сценарии](architecture/sequences.md)
- [Жизненный цикл файлов](architecture/file-data-lifecycle.md)
- [Структура Python package](architecture/target-package-layout.md)
- [ADR](adr/0001-package-boundaries.md)

## Слои

| Слой | Ответственность |
| --- | --- |
| `domain` | `AgentSpecification`, каталог компонентов, routing и runtime compiler |
| `application` | Сценарии, DTO, транзакции, файловые политики и порты |
| `builder` | Coordinator, специализированные агенты, function tools и сборка результата |
| `infrastructure` | Yandex AI Studio, SQLite, локальные файлы и logging |
| `presentation` | Streamlit и экспериментальный Telegram adapter |
| `entrypoints` | Запуск приложения через composition root |

Направления импортов проверяет `tests/test_architecture.py`. `domain` не зависит
от SDK и UI; `application` работает с внешними системами только через порты;
конкретные реализации связываются в `composition.py`.

## Сборка агента

1. UI создаёт `InteractionRequest` и передаёт его в
   `BuilderConversationService`.
2. Сервис копирует состояние диалога и выбирает one-prompt, RAG или coordinator.
3. Builder получает `RequestContext` без API-ключа и обновляет типизированный
   черновик через function tools.
4. RAG tool берёт файлы из серверного реестра, создаёт vector store и записывает
   подтверждённый `index_id` в спецификацию.
5. `finalize_agent_specification` возвращает результат только после
   детерминированной валидации.
6. `ResultAssembler` собирает текст и typed result parts.
7. Рабочее состояние коммитится только после успешной сборки результата.

Обычный текст модели не считается готовой спецификацией. Полный поток показан в
[sequence diagram](architecture/sequences.md).

## Preview

`AgentPreviewService` загружает `AgentSpecification`, проверяет её и компилирует
в `ExecutableAgentConfig`. Затем `AgentRunner` вызывает Responses API и
возвращает нормализованный ответ, citations и usage.

Для `web_search` compiler добавляет встроенный Web Search. Для RAG он добавляет
`file_search` с сохранённым `index_id`. Для Code Interpreter базовый config
содержит auto-container без `file_ids`; выбранные пользователем файлы
привязываются к копии config непосредственно перед запросом.

## Файлы и внешние ресурсы

Application layer отвечает за лимиты, upload, скачивание результатов и cleanup.
Runner не читает и не пишет пользовательские файлы.

- Builder, RAG и Code Interpreter используют разные наборы файлов.
- Remote IDs не попадают в `AgentSpecification` и экспорт.
- Частично записанные файлы удаляются при ошибке или превышении лимита.
- Известные remote resources удаляются в `finally`; TTL остаётся страховкой на
  случай недоступности API.

Лимиты и состояния ресурсов описаны в
[file lifecycle](architecture/file-data-lifecycle.md).

## Политика ответов

`domain/content_policy.py` задаёт общую политику для Builder и preview. Защита
применяется в несколько этапов:

1. детерминированная проверка запроса, метаданных вложений и импортируемой
   спецификации до обращения к модели;
2. приоритетные системные инструкции, которые считают сообщения, документы,
   результаты поиска и tool output недоверенными данными;
3. проверка Builder stream и собранных typed parts до коммита состояния;
4. проверка preview до показа citations; при ранней блокировке generated
   artifacts удаляются без скачивания, а в остальных случаях их поток
   проверяется до сохранения.

По умолчанию Builder и preview отвечают на русском. Другой язык допускается
только по явному запросу в рамках разрешённой задачи; стандартный отказ всегда
остаётся на русском.

При блокировке сервис возвращает нейтральный отказ и не записывает исходный
запрос или ответ в лог. Это defense-in-depth, а не доказательство отсутствия
всех возможных семантических обходов: набор регрессионных примеров должен
расширяться вместе с новыми наблюдаемыми атаками.

## Интерфейсы

Основной entrypoint — `ai_studio_agent_builder.entrypoints.web`. Telegram и
OAuth находятся в экспериментальных модулях и не запускаются автоматически.

Стабильная поверхность `0.1.0` ограничена `AgentSpecification`, JSON codec и
runtime compiler. UI, provider adapters и внутренние Builder tools не входят в
публичный Python API.

## Не входит в `0.1.0`

- постоянное хранилище спецификаций;
- создание постоянной Agent Atelier entity и возврат `agent_id`;
- multi-replica coordination;
- произвольные function и MCP tools;
- Code Interpreter с сетью или explicit containers.

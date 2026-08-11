# Каталог компонентов MVP

Каталог компонентов описывает только те шаблоны и элементы, которые Agent
Builder имеет право включать в экспортируемую `AgentSpecification`. Фактическая
реализация находится в
`src/ai_studio_agent_builder/domain/catalog.py`.

## Шаблоны

### `one_prompt`

Назначение: создать простое LLM-приложение, описываемое переиспользуемым system
prompt.

Обязательные поля спецификации:

- `purpose`;
- `instructions`;
- `expected_result`.

Компоненты:

- `system_prompt`;
- опциональный `web_search` для запросов, которым нужны актуальные данные из
  открытого интернета;
- опциональный `code_interpreter` для вычислений, анализа и преобразования
  явно выбранных файлов.

База знаний для этого шаблона не требуется. Обычный one-prompt остаётся без
tools; `web_search` добавляется только при явной потребности пользователя.

### `rag`

Назначение: создать LLM-приложение, которое использует базу знаний через
созданный vector index.

Обязательные поля спецификации:

- `purpose`;
- `instructions`;
- `expected_result`;
- `knowledge_sources`;
- `tools`;
- `parameters.index_id`.

Компоненты:

- `system_prompt`;
- `vector_index`;
- `knowledge_search`;
- опциональный `code_interpreter`.

## Публичные компоненты создаваемого агента

| Компонент | Тип | Попадает в `AgentSpecification` | Назначение |
| --- | --- | --- | --- |
| `system_prompt` | Prompt | Да | Инструкции и ограничения будущего агента. |
| `vector_index` | Knowledge base | Да, как `knowledge_sources` | Vector store AI Studio, созданный из загруженных файлов. |
| `knowledge_search` | Tool | Да, как публичный прикладной tool | Поиск по связанному `index_id`. |
| `web_search` | Tool | Да, как публичный встроенный tool | Поиск актуальной информации в интернете через Yandex AI Studio Responses API; vector index не требуется. |
| `code_interpreter` | Tool | Да, как переносимая capability | Python-вычисления и создание файлов в изолированном auto-container; spec содержит только `1g` и disabled network, но не file/container IDs. |

`file_search` и Code Interpreter решают разные задачи:

| | File Search | Code Interpreter |
| --- | --- | --- |
| Основная цель | Найти релевантные фрагменты в постоянной базе знаний. | Выполнить код, расчёт или преобразование файлов. |
| Состояние в spec | `index_id` является подтверждённой ссылкой RAG. | Только capability и безопасные параметры. |
| Пользовательские файлы | Индексируются в Vector Store. | Явно выбираются заново для каждого preview. |
| Remote IDs | `vector_store_id` переносится по RAG-контракту. | `file_id`/`container_id` никогда не экспортируются. |
| Результат | Текст и file citations. | Текст и локальные downloadable artifacts. |

## Внутренние tools конструктора

Следующие tools используются только Agent Builder и не являются прикладными
инструментами создаваемого агента:

- `delegate_rag`;
- `delegate_one_prompt`;
- `update_agent_specification`;
- `finalize_agent_specification`;
- `finish_dialog`;
- `create_search_index`.

`create_search_index` выполняет инфраструктурное действие конструктора. В
экспортируемой спецификации ему соответствует публичный tool
`knowledge_search`, связанный с фактически созданным `index_id`. Модель передаёт
только имя индекса; список файлов берётся из доверенного состояния RAG-сценария
и не входит в tool schema. Повторный вызов идемпотентно возвращает уже
привязанный индекс.

`update_agent_specification` и `finalize_agent_specification` управляют
черновиком и проверкой артефакта конструктора. Они не являются возможностями
создаваемого пользователем агента и поэтому не экспортируются в `tools`.

## Границы MVP

Каталог не является marketplace. Текущий объём ограничен двумя шаблонами и
минимальными компонентами: prompt, база знаний, `knowledge_search`, встроенный
`web_search` и безопасный `code_interpreter`. Произвольные function/MCP tools,
доступ Code Interpreter в сеть и explicit containers остаются за границами MVP.

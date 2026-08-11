# Ключевые sequence flows

## Построение AgentSpecification

```mermaid
sequenceDiagram
    actor User as Пользователь
    participant UI as Presentation
    participant App as BuilderConversationService
    participant Route as Domain routing
    participant Port as BuilderRunPort
    participant Adapter as Agents SDK adapter
    participant Tool as Function tool
    participant State as ConversationState
    participant Assemble as ResultAssembler

    User->>UI: Требования + optional files
    UI->>App: InteractionRequest
    App->>State: copy()
    App->>Route: resolve explicit intent
    App->>Port: run(BuilderRunRequest, working state)
    Port->>Adapter: injected implementation
    Adapter->>Tool: update/finalize specification
    Tool->>State: validate and update draft
    Adapter->>Assemble: normalized events + working state
    Assemble-->>Adapter: typed result parts
    Adapter-->>Port: BuilderRunOutcome
    Port-->>App: normalized outcome
    App->>State: commit_from(working state)
    App-->>UI: typed result parts
    UI-->>User: specification + developer bundle
```

При ошибке adapter, tool или assembly рабочая копия state не коммитится.
Application зависит только от `BuilderRunPort`; concrete Agents SDK adapter и
assembly находятся в слое builder.

## Текущий stateless preview

```mermaid
sequenceDiagram
    actor User as Пользователь
    participant UI as Streamlit
    participant Preview as Preview use case
    participant Compiler as Runtime compiler
    participant Runner as AgentRunner port
    participant Yandex as Responses adapter

    User->>UI: Specification + test input
    UI->>Preview: AgentTestRequest
    Preview->>Preview: strict import + readiness validation
    Preview->>Compiler: compile(specification)
    Compiler-->>Preview: ExecutableAgentConfig
    Preview->>Runner: run(config, input)
    Runner->>Yandex: Responses request
    Yandex-->>Runner: normalized preview DTO
    Runner-->>Preview: AgentRunPreview
    Preview-->>UI: AgentTestResult
    UI-->>User: text, citations, usage
```

## Реализованный Code Interpreter input preview (CI-3)

```mermaid
sequenceDiagram
    actor User as Пользователь
    participant UI as Presentation
    participant Preview as AgentPreviewService
    participant Files as PreviewInputFileLifecycle
    participant Gateway as FileResourceGateway
    participant Compiler as Runtime compiler
    participant Runner as AgentRunner
    participant API as Yandex AI Studio

    User->>UI: Specification + input + local file handles
    UI->>Preview: AgentTestRequest
    Preview->>Preview: strict import + input validation
    Preview->>Compiler: compile(specification)
    Compiler-->>Preview: base config without file IDs
    Preview->>Files: validate trusted attachments and quotas
    loop each accepted input file
        Files->>Gateway: create user_data file
        Gateway->>API: Files.create
        API-->>Gateway: remote file reference
        Gateway-->>Files: RemoteFileRef
    end
    Files->>Files: bind authorized refs to request copy
    Files-->>Preview: request-scoped config
    Preview->>Runner: run(config copy, input)
    Runner->>API: Responses.create with auto container
    API-->>Runner: raw response + citations
    Runner-->>Preview: AgentRunPreview
    Preview->>Files: leave context
    Files->>Gateway: delete all known remote input refs
    Preview-->>UI: AgentTestResult
    UI-->>User: text, citations and usage
```

Скачивание generated artifacts добавляется отдельно в CI-4. Оно использует ту
же ownership policy, но не меняет input binding и базовый runtime config.

## Failure semantics Code Interpreter

- Validation failure: provider не вызывается; локальные временные файлы не
  создаются либо удаляются владельцем request.
- Partial upload: все ранее созданные remote input files удаляются.
- Timeout/provider error: remote inputs и известные outputs удаляются;
  пользователю возвращается безопасная taxonomy error.
- Oversized output: чтение останавливается во время stream, partial local file
  удаляется, remote resource переходит в cleanup.
- Cleanup failure: основной успешный результат не теряется; фиксируется bounded
  warning/metric без credentials, file IDs и filenames.

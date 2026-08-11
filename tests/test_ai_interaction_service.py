import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai import OpenAIError

import ai_studio_agent_builder.application.file_lifecycle as file_lifecycle_module
from ai_studio_agent_builder.application.errors import AIStudioRequestError
from ai_studio_agent_builder.application.dto import AIStudioCredentials
from ai_studio_agent_builder.application.builder_state import ConversationState
from ai_studio_agent_builder.application.interaction import (
    AgentSpecificationImportError,
    AgentTestInputError,
    AgentTestRequest,
    Attachment,
    InteractionRequest,
    MAX_ATTACHMENTS_PER_REQUEST,
    UploadValidationError,
)
from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentCitation,
    AgentProviderError,
    AgentProviderTimeoutError,
    AgentRunPreview,
)
from ai_studio_agent_builder.application.ports.builder_run import BuilderRunOutcome
from ai_studio_agent_builder.config import (
    AIServiceConfig,
    AgentRuntimeConfig,
    ConnectionConfig,
    ModelConfig,
    PathConfig,
    SessionDBConfig,
)
from ai_studio_agent_builder.composition import build_ai_interaction_service
from ai_studio_agent_builder.domain.catalog import TemplateId
from ai_studio_agent_builder.domain.routing import ConversationOptions
from ai_studio_agent_builder.domain.runtime import (
    ExecutableAgentConfig,
    InvalidRuntimeFileBindingError,
)
from ai_studio_agent_builder.domain.specification import (
    AgentSpecification,
    KnowledgeSource,
    build_one_prompt_specification,
    build_rag_specification,
)


class FakeAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        if False:
            yield None


class DelegatingFakeAgent(FakeAgent):
    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        kwargs["context"].state.update_state(ConversationOptions.RAG)
        if False:
            yield None


class IndexCreatingFakeAgent(FakeAgent):
    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        yield SimpleNamespace(
            type="run_item_stream_event",
            name="tool_called",
            item=SimpleNamespace(
                raw_item={
                    "call_id": "call-index",
                    "name": "create_search_index",
                    "arguments": '{"vector_store_name":"knowledge"}',
                }
            ),
        )
        yield SimpleNamespace(
            type="run_item_stream_event",
            name="tool_output",
            item=SimpleNamespace(
                raw_item={"call_id": "call-index"},
                output=json.dumps(
                    {
                        "status": "created",
                        "index_id": "index-1",
                        "index_name": "knowledge",
                        "file_ids": ["file-first"],
                    }
                ),
            ),
        )


class FinalizingFakeAgent(FakeAgent):
    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        specification = build_one_prompt_specification(
            purpose="Draft concise support replies",
            instructions="Be concise and do not invent facts.",
            expected_result="Reusable support agent specification",
            web_search=True,
        )
        kwargs["context"].state.update_agent_specification(specification)
        finalized = kwargs["context"].state.finalize_agent_specification()
        kwargs["context"].state.finish_dialog()
        yield SimpleNamespace(
            type="run_item_stream_event",
            name="tool_called",
            item=SimpleNamespace(
                raw_item={
                    "call_id": "call-spec",
                    "name": "finalize_agent_specification",
                    "arguments": "{}",
                }
            ),
        )
        yield SimpleNamespace(
            type="run_item_stream_event",
            name="tool_output",
            item=SimpleNamespace(
                raw_item={"call_id": "call-spec"},
                output=json.dumps(finalized.to_record()),
            ),
        )


class SpecDelegatingFakeAgent(FakeAgent):
    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        kwargs["context"].state.update_agent_specification(
            AgentSpecification(
                template=TemplateId.RAG,
                purpose="Temporary draft",
            )
        )
        kwargs["context"].state.update_state(ConversationOptions.RAG)
        if False:
            yield None


class FailingFakeAgent(FakeAgent):
    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("agent failed")
        yield


class ProviderFailingFakeAgent(FakeAgent):
    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        raise OpenAIError("provider details")
        yield


class FakeGeneratedAgentRunner:
    def __init__(
        self,
        preview: AgentRunPreview | None = None,
        error: Exception | None = None,
    ) -> None:
        self.preview = preview or AgentRunPreview(
            response_id="resp-1",
            output_text="Generated answer",
        )
        self.error = error
        self.calls: list[tuple[ExecutableAgentConfig, str]] = []

    def run(self, config: ExecutableAgentConfig, user_input: str) -> AgentRunPreview:
        self.calls.append((config, user_input))
        if self.error is not None:
            raise self.error
        return self.preview


class FakeFileResourceGateway:
    def __init__(
        self,
        *,
        remote_ids: tuple[str, ...] = ("file-request-1", "file-request-2"),
        upload_error_at: int | None = None,
        cleanup_error: bool = False,
    ) -> None:
        self.remote_ids = remote_ids
        self.upload_error_at = upload_error_at
        self.cleanup_error = cleanup_error
        self.uploads: list[tuple[Path, str]] = []
        self.deleted: list[str] = []

    def upload_user_file(self, base_dir: Path, filename: str) -> str:
        self.uploads.append((base_dir, filename))
        if self.upload_error_at == len(self.uploads):
            raise AgentProviderError()
        return self.remote_ids[len(self.uploads) - 1]

    def delete_file(self, file_id: str) -> None:
        self.deleted.append(file_id)
        if self.cleanup_error:
            raise AgentProviderError()


class FakeFileResourceGatewayFactory:
    def __init__(self, gateway: FakeFileResourceGateway) -> None:
        self.gateway = gateway
        self.create_calls: list[AIStudioCredentials] = []

    def create(self, credentials: AIStudioCredentials) -> FakeFileResourceGateway:
        self.create_calls.append(credentials)
        return self.gateway


class FakeBuilderRunPort:
    def __init__(self) -> None:
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        selected_agent = request.conversation_state.state
        return BuilderRunOutcome(
            text="Builder response",
            parts=({"kind": "markdown", "text": "Builder response"},),
            selected_agent=selected_agent,
            responded_by=selected_agent,
            next_state=selected_agent,
        )


def _service_config(tmp_path: Path) -> AIServiceConfig:
    model = ModelConfig(
        model_name="test-model",
        temperature=0.0,
        max_output_tokens=10,
        base_url="https://example.test/v1",
        sessions_db_path=tmp_path / "sessions.db",
    )
    return AIServiceConfig(
        paths=PathConfig(uploaded_files_dir=tmp_path / "files"),
        connection=ConnectionConfig(base_url="https://example.test/v1", timeout=10),
        session_db_config=SessionDBConfig(path=tmp_path / "sessions.db"),
        rag_model=model,
        one_prompt=model,
        consultant=model,
        generated_agent_runtime=AgentRuntimeConfig(
            model_name="test-model",
            temperature=0.0,
            max_output_tokens=10,
        ),
    )


def _code_interpreter_specification_record() -> dict:
    return build_one_prompt_specification(
        purpose="Analyze uploaded data",
        instructions="Use code for checked calculations.",
        expected_result="A concise analysis",
        code_interpreter=True,
    ).to_record()


def test_service_routes_to_agent_selected_by_conversation_state(tmp_path: Path) -> None:
    coordinator = FakeAgent()
    rag = FakeAgent()
    one_prompt = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=coordinator,
        rag_agent=rag,
        one_prompt_agent=one_prompt,
    )
    state = ConversationState()
    state.update_state(ConversationOptions.RAG)

    result = asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="find this document",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key", folder_id="folder"
                ),
                conversation_state=state,
                user_files_dir=service.user_files_dir("42"),
            )
        )
    )

    assert result.selected_agent is ConversationOptions.RAG
    assert result.responded_by is ConversationOptions.RAG
    assert result.next_state is ConversationOptions.RAG
    assert coordinator.calls == []
    assert one_prompt.calls == []
    assert rag.calls[0]["message"] == "User request: find this document\n"
    assert rag.calls[0]["context"].folder_id == "folder"


def test_service_routes_through_application_owned_builder_port(tmp_path: Path) -> None:
    builder_run_port = FakeBuilderRunPort()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        builder_run_port=builder_run_port,
    )
    state = ConversationState(ConversationOptions.RAG)

    result = asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="Мне не нужен векторный поиск!",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key",
                    folder_id="folder",
                ),
                conversation_state=state,
                user_files_dir=service.user_files_dir("42"),
            )
        )
    )

    assert len(builder_run_port.requests) == 1
    assert builder_run_port.requests[0].conversation_state is not state
    assert builder_run_port.requests[0].conversation_state.state is (
        ConversationOptions.ONE_PROMPT
    )
    assert state.state is ConversationOptions.ONE_PROMPT
    assert result.text == "Builder response"
    assert result.parts == ({"kind": "markdown", "text": "Builder response"},)


def test_service_imports_ready_agent_specification_without_calling_an_agent(
    tmp_path: Path,
) -> None:
    coordinator = FakeAgent()
    rag = FakeAgent()
    one_prompt = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=coordinator,
        rag_agent=rag,
        one_prompt_agent=one_prompt,
    )
    # The source ID is intentionally distinct from the index ID. Import must
    # preserve that distinction and must not ask for a PDF.
    specification = AgentSpecification.from_record(
        build_rag_specification(
            purpose="Answer questions from the uploaded PDF",
            instructions="Search the connected index before answering.",
            expected_result="A concise answer with a source excerpt.",
            index_id="index-1",
            index_name="uploaded_pdf_index",
            knowledge_sources=(
                KnowledgeSource("file-1", "guide.pdf", "uploaded_file", "file-1"),
            ),
        ).to_record()
    )
    saved = service.save_attachment(
        "42",
        "agent-specification.json",
        json.dumps(specification.to_record(), ensure_ascii=False).encode(),
        caption="Создай агента из этой спецификации",
    )
    state = ConversationState()

    result = asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="Создай агента из этой спецификации",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key", folder_id="folder"
                ),
                conversation_state=state,
                user_files_dir=service.user_files_dir("42"),
                attachments=(saved,),
            )
        )
    )

    assert coordinator.calls == []
    assert rag.calls == []
    assert one_prompt.calls == []
    assert result.parts[0]["kind"] == "agent_specification"
    assert result.parts[0]["specification"] == specification.to_record()
    assert state.latest_agent_specification == specification
    assert result.next_state is ConversationOptions.RAG
    assert "PDF повторно загружать не требуется" in result.text


def test_service_reports_invalid_agent_specification_json_without_calling_agent(
    tmp_path: Path,
) -> None:
    coordinator = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=coordinator,
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
    )
    saved = service.save_attachment(
        "42",
        "agent-specification.json",
        b'{"template": "rag",',
        caption="Создай агента из этой спецификации",
    )

    with pytest.raises(AgentSpecificationImportError, match="некорректный JSON"):
        asyncio.run(
            service.interact(
                InteractionRequest(
                    user_id="42",
                    text="Создай агента из этой спецификации",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-key", folder_id="folder"
                    ),
                    conversation_state=ConversationState(),
                    user_files_dir=service.user_files_dir("42"),
                    attachments=(saved,),
                )
            )
        )

    assert coordinator.calls == []


def test_service_reports_non_object_specification_root_without_calling_agent(
    tmp_path: Path,
) -> None:
    coordinator = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=coordinator,
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
    )
    saved = service.save_attachment(
        "42",
        "agent-specification.json",
        b"[]",
        caption="Создай агента из этой спецификации",
    )

    with pytest.raises(
        AgentSpecificationImportError,
        match="Корень файла спецификации должен быть JSON-объектом",
    ):
        asyncio.run(
            service.interact(
                InteractionRequest(
                    user_id="42",
                    text="Создай агента из этой спецификации",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-key", folder_id="folder"
                    ),
                    conversation_state=ConversationState(),
                    user_files_dir=service.user_files_dir("42"),
                    attachments=(saved,),
                )
            )
        )

    assert coordinator.calls == []


def test_service_switches_sticky_rag_state_when_user_rejects_vector_search(
    tmp_path: Path,
) -> None:
    coordinator = FakeAgent()
    rag = FakeAgent()
    one_prompt = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=coordinator,
        rag_agent=rag,
        one_prompt_agent=one_prompt,
    )
    state = ConversationState(ConversationOptions.RAG)
    state.update_agent_specification(
        AgentSpecification(template=TemplateId.RAG, purpose="Stale RAG draft")
    )

    result = asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="Мне не нужен векторный поиск!",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key", folder_id="folder"
                ),
                conversation_state=state,
                user_files_dir=service.user_files_dir("42"),
            )
        )
    )

    assert result.selected_agent is ConversationOptions.ONE_PROMPT
    assert result.responded_by is ConversationOptions.ONE_PROMPT
    assert result.next_state is ConversationOptions.ONE_PROMPT
    assert state.state is ConversationOptions.ONE_PROMPT
    assert state.agent_specification is None
    assert coordinator.calls == []
    assert rag.calls == []
    assert one_prompt.calls[0]["message"] == (
        "User request: Мне не нужен векторный поиск!\n"
    )


def test_service_routes_web_search_without_vector_sources_to_one_prompt(
    tmp_path: Path,
) -> None:
    coordinator = FakeAgent()
    rag = FakeAgent()
    one_prompt = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=coordinator,
        rag_agent=rag,
        one_prompt_agent=one_prompt,
    )
    state = ConversationState()

    result = asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="Источником будет веб-поиск",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key", folder_id="folder"
                ),
                conversation_state=state,
                user_files_dir=service.user_files_dir("42"),
            )
        )
    )

    assert result.selected_agent is ConversationOptions.ONE_PROMPT
    assert result.responded_by is ConversationOptions.ONE_PROMPT
    assert result.next_state is ConversationOptions.ONE_PROMPT
    assert coordinator.calls == []
    assert rag.calls == []
    assert len(one_prompt.calls) == 1


def test_service_provides_a_shared_user_files_directory(tmp_path: Path) -> None:
    fake_agent = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=fake_agent,
        rag_agent=fake_agent,
        one_prompt_agent=fake_agent,
    )

    assert service.user_files_dir("web-connection") == (
        tmp_path / "files" / "web-connection"
    )


def test_service_returns_an_authoritative_vector_index_part(tmp_path: Path) -> None:
    rag = IndexCreatingFakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=rag,
        one_prompt_agent=FakeAgent(),
    )
    state = ConversationState()
    state.update_state(ConversationOptions.RAG)

    result = asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="Create an index",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key", folder_id="folder"
                ),
                conversation_state=state,
                user_files_dir=service.user_files_dir("42"),
                attachments=(
                    Attachment(
                        filename="internal-first.pdf",
                        display_name="first.pdf",
                        file_id="file-first",
                    ),
                ),
            )
        )
    )

    assert result.parts[0] == {
        "kind": "vector_index",
        "index_name": "knowledge",
        "index_id": "index-1",
        "expires_after_days": 1,
        "files": [{"filename": "first.pdf", "file_id": "file-first"}],
    }
    assert len(result.parts) == 1
    assert rag.calls[0]["context"].allowed_file_ids == frozenset({"file-first"})


def test_service_keeps_uploaded_files_available_for_next_rag_turn(
    tmp_path: Path,
) -> None:
    rag = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=rag,
        one_prompt_agent=FakeAgent(),
    )
    state = ConversationState(ConversationOptions.RAG)

    asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="Use this document",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key", folder_id="folder"
                ),
                conversation_state=state,
                user_files_dir=service.user_files_dir("42"),
                attachments=(
                    Attachment(
                        filename="internal-first.pdf",
                        display_name="first.pdf",
                        file_id="file-first",
                    ),
                ),
            )
        )
    )
    asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="Call it faq_index",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key", folder_id="folder"
                ),
                conversation_state=state,
                user_files_dir=service.user_files_dir("42"),
            )
        )
    )

    second_context = rag.calls[1]["context"]
    assert second_context.allowed_file_ids == frozenset({"file-first"})
    assert second_context.filenames_by_file_id == {"file-first": "first.pdf"}
    assert "first.pdf" in rag.calls[1]["message"]
    assert "file-first" not in rag.calls[1]["message"]


def test_service_commits_and_exports_only_finalized_specification(
    tmp_path: Path,
) -> None:
    one_prompt = FinalizingFakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=one_prompt,
    )
    state = ConversationState(ConversationOptions.ONE_PROMPT)

    result = asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="Create a support agent",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key", folder_id="folder"
                ),
                conversation_state=state,
                user_files_dir=service.user_files_dir("42"),
            )
        )
    )

    assert len(result.parts) == 1
    specification_record = result.parts[0]["specification"]
    assert specification_record["purpose"] == "Draft concise support replies"
    assert [tool["tool_id"] for tool in specification_record["tools"]] == ["web_search"]
    assert state.latest_agent_specification is not None
    assert state.latest_agent_specification.to_record() == specification_record
    assert result.next_state is ConversationOptions.COORDINATOR
    assert state.state is ConversationOptions.COORDINATOR


def test_service_saves_upload_in_the_user_directory(tmp_path: Path) -> None:
    fake_agent = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=fake_agent,
        rag_agent=fake_agent,
        one_prompt_agent=fake_agent,
    )

    attachment = service.save_attachment(
        "web-connection", "../report.txt", b"data", caption="Index this"
    )

    assert attachment.filename.endswith("_report.txt")
    assert attachment.display_name == "report.txt"
    assert attachment.caption == "Index this"
    assert (
        service.user_files_dir("web-connection") / attachment.filename
    ).read_bytes() == b"data"


def test_service_sanitizes_unsafe_display_filename(tmp_path: Path) -> None:
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
    )

    attachment = service.save_attachment(
        "web-connection",
        "..\\..// bad:\x00name?.txt ",
        b"data",
    )

    assert attachment.display_name == "bad_name_.txt"
    assert "/" not in attachment.filename
    assert ".." not in Path(attachment.filename).parts


def test_service_builds_a_single_request_for_multiple_uploaded_files(
    tmp_path: Path,
) -> None:
    coordinator = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=coordinator,
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
    )
    request = InteractionRequest(
        user_id="42",
        text="Create an index",
        credentials=AIStudioCredentials(api_key="AQAAAA-key", folder_id="folder"),
        conversation_state=ConversationState(),
        user_files_dir=tmp_path,
        attachments=(
            Attachment(filename="first.pdf", caption="Create an index"),
            Attachment(filename="second.pdf", caption="Create an index"),
        ),
    )

    asyncio.run(service.interact(request))

    assert coordinator.calls[0]["message"] == (
        "Uploaded files by user: first.pdf, second.pdf with request: Create an index\n"
    )


def test_service_reuses_uploaded_files_after_coordinator_delegates_to_rag(
    tmp_path: Path,
) -> None:
    coordinator = DelegatingFakeAgent()
    rag = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=coordinator,
        rag_agent=rag,
        one_prompt_agent=FakeAgent(),
    )
    request = InteractionRequest(
        user_id="42",
        text="Create an index",
        credentials=AIStudioCredentials(api_key="AQAAAA-key", folder_id="folder"),
        conversation_state=ConversationState(),
        user_files_dir=service.user_files_dir("42"),
        attachments=(
            Attachment(filename="first.pdf", file_id="file-first"),
            Attachment(filename="second.pdf", file_id="file-second"),
        ),
    )

    asyncio.run(service.interact(request))

    assert len(coordinator.calls) == 1
    assert rag.calls[0]["message"] == (
        "Files are securely available for this RAG workflow: first.pdf, second.pdf. "
        "Create the requested vector index using the server-managed files; do not "
        "ask the user to upload them again and do not request file IDs. "
        "User request: Create an index\n"
    )
    assert rag.calls[0]["context"].allowed_file_ids == frozenset(
        {"file-first", "file-second"}
    )
    assert request.conversation_state.state is ConversationOptions.RAG


def test_service_commits_conversation_state_only_after_success(tmp_path: Path) -> None:
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=DelegatingFakeAgent(),
        rag_agent=FailingFakeAgent(),
        one_prompt_agent=FakeAgent(),
    )
    state = ConversationState()

    with pytest.raises(RuntimeError, match="agent failed"):
        asyncio.run(
            service.interact(
                InteractionRequest(
                    user_id="42",
                    text="Create an index",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-key", folder_id="folder"
                    ),
                    conversation_state=state,
                    user_files_dir=service.user_files_dir("42"),
                )
            )
        )

    assert state.state is ConversationOptions.COORDINATOR


def test_service_maps_provider_failure_to_application_error(tmp_path: Path) -> None:
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=ProviderFailingFakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
    )

    with pytest.raises(AIStudioRequestError) as exc_info:
        asyncio.run(
            service.interact(
                InteractionRequest(
                    user_id="42",
                    text="Hello",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-key", folder_id="folder"
                    ),
                    conversation_state=ConversationState(),
                    user_files_dir=service.user_files_dir("42"),
                )
            )
        )

    assert isinstance(exc_info.value.__cause__, OpenAIError)
    assert "provider details" not in str(exc_info.value)


def test_connection_validation_maps_provider_failure_to_application_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_connection(**kwargs) -> None:
        raise OpenAIError("provider details")

    client = SimpleNamespace(
        responses=SimpleNamespace(create=reject_connection),
    )
    monkeypatch.setattr(
        "ai_studio_agent_builder.composition.get_api_key_client",
        lambda credentials, config: client,
    )
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
    )

    with pytest.raises(AIStudioRequestError) as exc_info:
        asyncio.run(
            service.validate_connection(
                AIStudioCredentials(api_key="AQAAAA-key", folder_id="folder")
            )
        )

    assert isinstance(exc_info.value.__cause__, OpenAIError)
    assert "provider details" not in str(exc_info.value)


def test_service_does_not_commit_specification_draft_after_failure(
    tmp_path: Path,
) -> None:
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=SpecDelegatingFakeAgent(),
        rag_agent=FailingFakeAgent(),
        one_prompt_agent=FakeAgent(),
    )
    state = ConversationState()

    with pytest.raises(RuntimeError, match="agent failed"):
        asyncio.run(
            service.interact(
                InteractionRequest(
                    user_id="42",
                    text="Create a RAG agent",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-key", folder_id="folder"
                    ),
                    conversation_state=state,
                    user_files_dir=service.user_files_dir("42"),
                )
            )
        )

    assert state.state is ConversationOptions.COORDINATOR
    assert state.agent_specification is None


def test_service_context_uses_request_id_without_exposing_api_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    agent = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=agent,
        rag_agent=agent,
        one_prompt_agent=agent,
    )

    with caplog.at_level("INFO"):
        asyncio.run(
            service.interact(
                InteractionRequest(
                    user_id="42",
                    request_id="request-42",
                    text="Hello",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-super-secret", folder_id="folder"
                    ),
                    conversation_state=ConversationState(),
                    user_files_dir=service.user_files_dir("42"),
                )
            )
        )

    context = agent.calls[0]["context"]
    assert context.request_id == "request-42"
    assert not hasattr(context, "api_key")
    assert any(
        getattr(record, "request_id", None) == "request-42" for record in caplog.records
    )
    assert "AQAAAA-super-secret" not in caplog.text


def test_service_uploads_files_before_running_rag_after_delegation(
    tmp_path: Path,
) -> None:
    coordinator = DelegatingFakeAgent()
    rag = FakeAgent()
    files_dir = tmp_path / "files" / "42"
    files_dir.mkdir(parents=True)
    (files_dir / "first.pdf").write_bytes(b"first")
    (files_dir / "second.pdf").write_bytes(b"second")
    uploaded: list[str] = []

    def fake_upload_file(_client, base_dir: Path, filename: str) -> str:
        assert base_dir == files_dir
        assert (base_dir / filename).read_bytes()
        uploaded.append(filename)
        return f"file-{filename}"

    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=coordinator,
        rag_agent=rag,
        one_prompt_agent=FakeAgent(),
        file_uploader=fake_upload_file,
    )

    asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="Create an index",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key", folder_id="folder"
                ),
                conversation_state=ConversationState(),
                user_files_dir=files_dir,
                attachments=(
                    Attachment(filename="first.pdf"),
                    Attachment(filename="second.pdf"),
                ),
            )
        )
    )

    assert uploaded == ["first.pdf", "second.pdf"]
    assert "first.pdf, second.pdf" in rag.calls[0]["message"]
    assert "file-first.pdf" not in rag.calls[0]["message"]
    assert "file-second.pdf" not in rag.calls[0]["message"]
    assert rag.calls[0]["context"].allowed_file_ids == frozenset(
        {"file-first.pdf", "file-second.pdf"}
    )


def test_service_rejects_non_current_request_paths_before_upload(
    tmp_path: Path,
) -> None:
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
    )
    state = ConversationState()
    state.update_state(ConversationOptions.RAG)

    with pytest.raises(UploadValidationError):
        asyncio.run(
            service.interact(
                InteractionRequest(
                    user_id="42",
                    text="Create an index",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-key", folder_id="folder"
                    ),
                    conversation_state=state,
                    user_files_dir=service.user_files_dir("42"),
                    attachments=(Attachment(filename="../stale.pdf"),),
                )
            )
        )


def test_service_rejects_preview_artifacts_before_upload(tmp_path: Path) -> None:
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
    )
    state = ConversationState()
    state.update_state(ConversationOptions.RAG)

    with pytest.raises(UploadValidationError):
        asyncio.run(
            service.interact(
                InteractionRequest(
                    user_id="42",
                    text="Create an index",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-key", folder_id="folder"
                    ),
                    conversation_state=state,
                    user_files_dir=service.user_files_dir("42"),
                    attachments=(Attachment(filename=".previews/page.png"),),
                )
            )
        )


def test_service_limits_attachments_per_request(tmp_path: Path) -> None:
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
    )
    state = ConversationState(ConversationOptions.RAG)
    attachments = tuple(
        Attachment(filename=f"file-{index}.txt")
        for index in range(MAX_ATTACHMENTS_PER_REQUEST + 1)
    )

    with pytest.raises(UploadValidationError):
        asyncio.run(
            service.interact(
                InteractionRequest(
                    user_id="42",
                    text="Create an index",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-key",
                        folder_id="folder",
                    ),
                    conversation_state=state,
                    user_files_dir=service.user_files_dir("42"),
                    attachments=attachments,
                )
            )
        )


def test_service_disables_sensitive_tracing(tmp_path: Path) -> None:
    rag = FakeAgent()
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=rag,
        one_prompt_agent=FakeAgent(),
    )
    state = ConversationState()
    state.update_state(ConversationOptions.RAG)

    asyncio.run(
        service.interact(
            InteractionRequest(
                user_id="42",
                text="Create an index",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-key", folder_id="folder"
                ),
                conversation_state=state,
                user_files_dir=service.user_files_dir("42"),
            )
        )
    )

    run_config = rag.calls[0]["run_config"]
    assert run_config.tracing_disabled is True
    assert run_config.trace_include_sensitive_data is False


def test_reset_conversation_removes_saved_uploads(tmp_path: Path) -> None:
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
    )
    saved = service.save_attachment("42", "report.txt", b"data")
    saved_path = service.user_files_dir("42") / saved.filename
    assert saved_path.exists()

    asyncio.run(service.reset_conversation("42"))

    assert not service.user_files_dir("42").exists()


def test_service_runs_serialized_specification_without_mutating_builder_state(
    tmp_path: Path,
) -> None:
    preview = AgentRunPreview(
        response_id="resp-42",
        output_text="Grounded answer",
        citations=(
            AgentCitation(
                kind="url",
                title="Source",
                url="https://example.test/source",
            ),
        ),
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
    )
    runner = FakeGeneratedAgentRunner(preview)
    factory_calls: list[tuple[object, str]] = []

    def runner_factory(client, folder_id: str):
        factory_calls.append((client, folder_id))
        return runner

    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=runner_factory,
    )
    builder_state = ConversationState()
    existing_specification = build_one_prompt_specification(
        purpose="Existing builder result",
        instructions="Keep unchanged.",
        expected_result="Existing result",
    )
    builder_state.update_agent_specification(existing_specification)
    state_before = builder_state.copy()
    specification_record = build_one_prompt_specification(
        purpose="Draft support replies",
        instructions="Be concise.",
        expected_result="Reply",
        web_search=True,
    ).to_record()

    result = asyncio.run(
        service.test_agent_specification(
            AgentTestRequest(
                user_id="user@example.test",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-secret", folder_id="folder-1"
                ),
                specification_record=specification_record,
                user_input="  Test question  ",
            )
        )
    )

    assert result.response_id == "resp-42"
    assert result.output_text == "Grounded answer"
    assert result.citations == preview.citations
    assert result.total_tokens == 15
    assert len(factory_calls) == 1
    assert factory_calls[0][1] == "folder-1"
    assert len(runner.calls) == 1
    executable_config, user_input = runner.calls[0]
    assert user_input == "Test question"
    assert executable_config.tools == (
        {"type": "web_search", "search_context_size": "medium"},
    )
    exported_config = service.prepare_agent_runtime(specification_record)
    assert exported_config == executable_config
    assert "folder-1" not in exported_config.to_json()
    assert "AQAAAA-secret" not in exported_config.to_json()
    assert builder_state.state is state_before.state
    assert builder_state.agent_specification == state_before.agent_specification


def test_service_binds_preview_files_to_request_copy_and_cleans_remote_inputs(
    tmp_path: Path,
) -> None:
    runner = FakeGeneratedAgentRunner()
    gateway = FakeFileResourceGateway()
    gateway_factory = FakeFileResourceGatewayFactory(gateway)
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=lambda client, folder_id: runner,
        file_resource_gateway_factory=gateway_factory,
    )
    first = service.save_attachment("42", "sales.csv", b"amount\n10\n")
    second = service.save_attachment("42", "rates.txt", b"rate=2")
    specification_record = _code_interpreter_specification_record()
    base_config = service.prepare_agent_runtime(specification_record)
    base_json = base_config.to_json()
    credentials = AIStudioCredentials(
        api_key="AQAAAA-secret",
        folder_id="folder-1",
    )

    result = asyncio.run(
        service.test_agent_specification(
            AgentTestRequest(
                user_id="42",
                credentials=credentials,
                specification_record=specification_record,
                user_input="Calculate the converted total",
                attachments=(first, second),
            )
        )
    )

    assert result.response_id == "resp-1"
    assert gateway_factory.create_calls == [credentials]
    assert gateway.uploads == [
        (service.user_files_dir("42"), first.filename),
        (service.user_files_dir("42"), second.filename),
    ]
    assert gateway.deleted == ["file-request-1", "file-request-2"]
    request_config, user_input = runner.calls[0]
    assert user_input == "Calculate the converted total"
    assert request_config.tools[0]["container"]["file_ids"] == [
        "file-request-1",
        "file-request-2",
    ]
    assert base_config.to_json() == base_json
    assert service.prepare_agent_runtime(specification_record).to_json() == base_json


def test_service_uses_auto_container_without_files_or_gateway_call(
    tmp_path: Path,
) -> None:
    runner = FakeGeneratedAgentRunner()
    gateway_factory = FakeFileResourceGatewayFactory(FakeFileResourceGateway())
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=lambda client, folder_id: runner,
        file_resource_gateway_factory=gateway_factory,
    )

    asyncio.run(
        service.test_agent_specification(
            AgentTestRequest(
                user_id="42",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-secret",
                    folder_id="folder-1",
                ),
                specification_record=_code_interpreter_specification_record(),
                user_input="Use file-secret-from-prompt and calculate 2 + 2",
            )
        )
    )

    assert gateway_factory.create_calls == []
    container = runner.calls[0][0].tools[0]["container"]
    assert container == {
        "type": "auto",
        "memory_limit": "1g",
        "network_policy": {"type": "disabled"},
    }


def test_service_rejects_attachments_without_code_interpreter_before_provider_call(
    tmp_path: Path,
) -> None:
    gateway_factory = FakeFileResourceGatewayFactory(FakeFileResourceGateway())
    runner_factory_calls: list[tuple[object, str]] = []

    def runner_factory(client, folder_id: str):
        runner_factory_calls.append((client, folder_id))
        return FakeGeneratedAgentRunner()

    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=runner_factory,
        file_resource_gateway_factory=gateway_factory,
    )
    attachment = service.save_attachment("42", "input.csv", b"value\n1\n")

    with pytest.raises(AgentTestInputError):
        asyncio.run(
            service.test_agent_specification(
                AgentTestRequest(
                    user_id="42",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-secret",
                        folder_id="folder-1",
                    ),
                    specification_record=build_one_prompt_specification(
                        purpose="Draft replies",
                        instructions="Be concise.",
                        expected_result="Reply",
                    ).to_record(),
                    user_input="Analyze this file",
                    attachments=(attachment,),
                )
            )
        )

    assert gateway_factory.create_calls == []
    assert runner_factory_calls == []


@pytest.mark.parametrize(
    "attachments",
    [
        (Attachment(filename="../outside.csv"),),
        (Attachment(filename="safe.csv", file_id="file-injected"),),
        tuple(Attachment(filename=f"file-{index}.csv") for index in range(6)),
    ],
)
def test_service_rejects_untrusted_preview_attachment_metadata_before_upload(
    tmp_path: Path,
    attachments: tuple[Attachment, ...],
) -> None:
    gateway_factory = FakeFileResourceGatewayFactory(FakeFileResourceGateway())
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=lambda client, folder_id: FakeGeneratedAgentRunner(),
        file_resource_gateway_factory=gateway_factory,
    )

    with pytest.raises(AgentTestInputError):
        asyncio.run(
            service.test_agent_specification(
                AgentTestRequest(
                    user_id="42",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-secret",
                        folder_id="folder-1",
                    ),
                    specification_record=_code_interpreter_specification_record(),
                    user_input="Analyze the inputs",
                    attachments=attachments,
                )
            )
        )

    assert gateway_factory.create_calls == []


def test_service_validates_total_attachment_size_before_upload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_lifecycle_module, "MAX_TOTAL_UPLOAD_BYTES", 5)
    gateway_factory = FakeFileResourceGatewayFactory(FakeFileResourceGateway())
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=lambda client, folder_id: FakeGeneratedAgentRunner(),
        file_resource_gateway_factory=gateway_factory,
    )
    first = service.save_attachment("42", "first.txt", b"123")
    second = service.save_attachment("42", "second.txt", b"456")

    with pytest.raises(AgentTestInputError):
        asyncio.run(
            service.test_agent_specification(
                AgentTestRequest(
                    user_id="42",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-secret",
                        folder_id="folder-1",
                    ),
                    specification_record=_code_interpreter_specification_record(),
                    user_input="Analyze the inputs",
                    attachments=(first, second),
                )
            )
        )

    assert gateway_factory.create_calls == []


def test_service_cleans_completed_uploads_after_partial_upload_failure(
    tmp_path: Path,
) -> None:
    gateway = FakeFileResourceGateway(upload_error_at=2)
    gateway_factory = FakeFileResourceGatewayFactory(gateway)
    runner_factory_calls: list[tuple[object, str]] = []

    def runner_factory(client, folder_id: str):
        runner_factory_calls.append((client, folder_id))
        return FakeGeneratedAgentRunner()

    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=runner_factory,
        file_resource_gateway_factory=gateway_factory,
    )
    first = service.save_attachment("42", "first.txt", b"1")
    second = service.save_attachment("42", "second.txt", b"2")

    with pytest.raises(AgentProviderError):
        asyncio.run(
            service.test_agent_specification(
                AgentTestRequest(
                    user_id="42",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-secret",
                        folder_id="folder-1",
                    ),
                    specification_record=_code_interpreter_specification_record(),
                    user_input="Analyze",
                    attachments=(first, second),
                )
            )
        )

    assert gateway.deleted == ["file-request-1"]
    assert runner_factory_calls == []


@pytest.mark.parametrize(
    ("runner_error", "expected_error"),
    [
        (AgentProviderError(), AgentProviderError),
        (AgentProviderTimeoutError(), AgentProviderTimeoutError),
        (RuntimeError("provider-secret"), AgentProviderError),
    ],
)
def test_service_cleans_remote_inputs_after_runner_failure(
    tmp_path: Path,
    runner_error: Exception,
    expected_error: type[Exception],
) -> None:
    gateway = FakeFileResourceGateway()
    runner = FakeGeneratedAgentRunner(error=runner_error)
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=lambda client, folder_id: runner,
        file_resource_gateway_factory=FakeFileResourceGatewayFactory(gateway),
    )
    attachment = service.save_attachment("42", "input.txt", b"1")

    with pytest.raises(expected_error):
        asyncio.run(
            service.test_agent_specification(
                AgentTestRequest(
                    user_id="42",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-secret",
                        folder_id="folder-1",
                    ),
                    specification_record=_code_interpreter_specification_record(),
                    user_input="Analyze",
                    attachments=(attachment,),
                )
            )
        )

    assert gateway.deleted == ["file-request-1"]


def test_service_cleans_remote_inputs_when_runner_factory_fails(tmp_path: Path) -> None:
    gateway = FakeFileResourceGateway()

    def failing_runner_factory(client, folder_id: str):
        raise RuntimeError("provider-secret")

    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=failing_runner_factory,
        file_resource_gateway_factory=FakeFileResourceGatewayFactory(gateway),
    )
    attachment = service.save_attachment("42", "input.txt", b"1")

    with pytest.raises(AgentProviderError):
        asyncio.run(
            service.test_agent_specification(
                AgentTestRequest(
                    user_id="42",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-secret",
                        folder_id="folder-1",
                    ),
                    specification_record=_code_interpreter_specification_record(),
                    user_input="Analyze",
                    attachments=(attachment,),
                )
            )
        )

    assert gateway.deleted == ["file-request-1"]


def test_service_cleans_remote_inputs_when_runtime_binding_fails(
    tmp_path: Path,
) -> None:
    gateway = FakeFileResourceGateway(remote_ids=("file-duplicate", "file-duplicate"))
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=lambda client, folder_id: FakeGeneratedAgentRunner(),
        file_resource_gateway_factory=FakeFileResourceGatewayFactory(gateway),
    )
    first = service.save_attachment("42", "first.txt", b"1")
    second = service.save_attachment("42", "second.txt", b"2")

    with pytest.raises(InvalidRuntimeFileBindingError):
        asyncio.run(
            service.test_agent_specification(
                AgentTestRequest(
                    user_id="42",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-secret",
                        folder_id="folder-1",
                    ),
                    specification_record=_code_interpreter_specification_record(),
                    user_input="Analyze",
                    attachments=(first, second),
                )
            )
        )
    assert gateway.deleted == ["file-duplicate", "file-duplicate"]


def test_service_preserves_success_when_remote_input_cleanup_fails(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    gateway = FakeFileResourceGateway(cleanup_error=True)
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=lambda client, folder_id: FakeGeneratedAgentRunner(),
        file_resource_gateway_factory=FakeFileResourceGatewayFactory(gateway),
    )
    attachment = service.save_attachment("42", "private-input.txt", b"1")

    result = asyncio.run(
        service.test_agent_specification(
            AgentTestRequest(
                user_id="42",
                credentials=AIStudioCredentials(
                    api_key="AQAAAA-secret",
                    folder_id="folder-1",
                ),
                specification_record=_code_interpreter_specification_record(),
                user_input="Analyze",
                attachments=(attachment,),
            )
        )
    )

    assert result.response_id == "resp-1"
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "file-request-1" not in log_text
    assert attachment.filename not in log_text


def test_service_strictly_parses_specification_before_creating_runner(
    tmp_path: Path,
) -> None:
    factory_calls: list[tuple[object, str]] = []

    def runner_factory(client, folder_id: str):
        factory_calls.append((client, folder_id))
        return FakeGeneratedAgentRunner()

    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=runner_factory,
    )
    malformed_record = build_one_prompt_specification(
        purpose="Draft replies",
        instructions="Be concise.",
        expected_result="Reply",
    ).to_record()
    malformed_record["unexpected"] = True

    with pytest.raises(ValueError):
        asyncio.run(
            service.test_agent_specification(
                AgentTestRequest(
                    user_id="42",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-secret", folder_id="folder-1"
                    ),
                    specification_record=malformed_record,
                    user_input="Question",
                )
            )
        )

    assert factory_calls == []


@pytest.mark.parametrize("user_input", ["", "   ", "x" * 10_001])
def test_service_rejects_invalid_agent_test_input(
    tmp_path: Path, user_input: str
) -> None:
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=lambda client, folder_id: FakeGeneratedAgentRunner(),
    )

    with pytest.raises(AgentTestInputError):
        asyncio.run(
            service.test_agent_specification(
                AgentTestRequest(
                    user_id="42",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-secret", folder_id="folder-1"
                    ),
                    specification_record=build_one_prompt_specification(
                        purpose="Draft replies",
                        instructions="Be concise.",
                        expected_result="Reply",
                    ).to_record(),
                    user_input=user_input,
                )
            )
        )


def test_service_hides_unexpected_runner_error_details(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runner = FakeGeneratedAgentRunner(
        error=RuntimeError("api_key=AQAAAA-secret-provider-body")
    )
    service = build_ai_interaction_service(
        _service_config(tmp_path),
        coordinator_agent=FakeAgent(),
        rag_agent=FakeAgent(),
        one_prompt_agent=FakeAgent(),
        agent_runner_factory=lambda client, folder_id: runner,
    )

    with pytest.raises(AgentProviderError) as exc_info:
        asyncio.run(
            service.test_agent_specification(
                AgentTestRequest(
                    user_id="real-user-id",
                    credentials=AIStudioCredentials(
                        api_key="AQAAAA-secret", folder_id="folder-1"
                    ),
                    specification_record=build_one_prompt_specification(
                        purpose="Draft replies",
                        instructions="Be concise.",
                        expected_result="Reply",
                    ).to_record(),
                    user_input="Question",
                )
            )
        )

    assert "secret" not in str(exc_info.value)
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "secret-provider-body" not in log_text
    assert "real-user-id" not in log_text

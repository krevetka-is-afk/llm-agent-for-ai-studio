import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_runner import AgentCitation, AgentProviderError, AgentRunPreview
from agent_runtime import ExecutableAgentConfig
from agent_specification import (
    AgentSpecification,
    KnowledgeSource,
    build_one_prompt_specification,
    build_rag_specification,
)
from component_catalog import TemplateId
from ai_interaction_service import (
    AIInteractionService,
    AgentSpecificationImportError,
    AgentTestInputError,
    AgentTestRequest,
    Attachment,
    InteractionRequest,
    MAX_ATTACHMENTS_PER_REQUEST,
    UploadValidationError,
)
from config import (
    AgentRuntimeConfig,
    AIServiceConfig,
    ConnectionConfig,
    ModelConfig,
    PathConfig,
    SessionDBConfig,
)
from context import AIStudioCredentials, ConversationOptions, ConversationState
from result_assembly import (
    AgentSpecificationResultPart,
    IndexedFileResult,
    VectorIndexResultPart,
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


def test_service_routes_to_agent_selected_by_conversation_state(tmp_path: Path) -> None:
    coordinator = FakeAgent()
    rag = FakeAgent()
    one_prompt = FakeAgent()
    service = AIInteractionService(
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


def test_service_imports_ready_agent_specification_without_calling_an_agent(
    tmp_path: Path,
) -> None:
    coordinator = FakeAgent()
    rag = FakeAgent()
    one_prompt = FakeAgent()
    service = AIInteractionService(
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
    assert isinstance(result.parts[0], AgentSpecificationResultPart)
    assert result.parts[0].specification == specification
    assert state.latest_agent_specification == specification
    assert result.next_state is ConversationOptions.RAG
    assert "PDF повторно загружать не требуется" in result.text


def test_service_reports_invalid_agent_specification_json_without_calling_agent(
    tmp_path: Path,
) -> None:
    coordinator = FakeAgent()
    service = AIInteractionService(
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


def test_service_switches_sticky_rag_state_when_user_rejects_vector_search(
    tmp_path: Path,
) -> None:
    coordinator = FakeAgent()
    rag = FakeAgent()
    one_prompt = FakeAgent()
    service = AIInteractionService(
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
    service = AIInteractionService(
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
    service = AIInteractionService(
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
    service = AIInteractionService(
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

    assert result.parts[0] == VectorIndexResultPart(
        index_name="knowledge",
        index_id="index-1",
        files=(IndexedFileResult("first.pdf", "file-first"),),
        expires_after_days=1,
    )
    assert len(result.parts) == 1
    assert rag.calls[0]["context"].allowed_file_ids == frozenset({"file-first"})


def test_service_keeps_uploaded_files_available_for_next_rag_turn(
    tmp_path: Path,
) -> None:
    rag = FakeAgent()
    service = AIInteractionService(
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
    service = AIInteractionService(
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
    assert isinstance(result.parts[0], AgentSpecificationResultPart)
    assert result.parts[0].specification.purpose == "Draft concise support replies"
    assert [tool.tool_id for tool in result.parts[0].specification.tools] == [
        "web_search"
    ]
    assert state.latest_agent_specification == result.parts[0].specification
    assert result.next_state is ConversationOptions.COORDINATOR
    assert state.state is ConversationOptions.COORDINATOR


def test_service_saves_upload_in_the_user_directory(tmp_path: Path) -> None:
    fake_agent = FakeAgent()
    service = AIInteractionService(
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
    service = AIInteractionService(
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

    assert AIInteractionService._build_input(request) == (
        "Uploaded files by user: first.pdf, second.pdf with request: Create an index\n"
    )


def test_service_reuses_uploaded_files_after_coordinator_delegates_to_rag(
    tmp_path: Path,
) -> None:
    coordinator = DelegatingFakeAgent()
    rag = FakeAgent()
    service = AIInteractionService(
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
    service = AIInteractionService(
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


def test_service_does_not_commit_specification_draft_after_failure(
    tmp_path: Path,
) -> None:
    service = AIInteractionService(
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
    service = AIInteractionService(
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
    tmp_path: Path, monkeypatch
) -> None:
    coordinator = DelegatingFakeAgent()
    rag = FakeAgent()
    service = AIInteractionService(
        _service_config(tmp_path),
        coordinator_agent=coordinator,
        rag_agent=rag,
        one_prompt_agent=FakeAgent(),
    )
    files_dir = service.user_files_dir("42")
    files_dir.mkdir(parents=True)
    (files_dir / "first.pdf").write_bytes(b"first")
    (files_dir / "second.pdf").write_bytes(b"second")
    uploaded: list[str] = []

    def fake_upload_file(_client, base_dir: Path, filename: str) -> str:
        assert base_dir == files_dir
        assert (base_dir / filename).read_bytes()
        uploaded.append(filename)
        return f"file-{filename}"

    monkeypatch.setattr("ai_interaction_service.upload_local_file", fake_upload_file)

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
    service = AIInteractionService(
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
    service = AIInteractionService(
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
    attachments = tuple(
        Attachment(filename=f"file-{index}.txt")
        for index in range(MAX_ATTACHMENTS_PER_REQUEST + 1)
    )

    with pytest.raises(UploadValidationError):
        asyncio.run(
            AIInteractionService._ensure_uploaded_files(
                attachments,
                client=object(),
                base_dir=tmp_path,
            )
        )


def test_service_disables_sensitive_tracing(tmp_path: Path) -> None:
    rag = FakeAgent()
    service = AIInteractionService(
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
    service = AIInteractionService(
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

    service = AIInteractionService(
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


def test_service_strictly_parses_specification_before_creating_runner(
    tmp_path: Path,
) -> None:
    factory_calls: list[tuple[object, str]] = []

    def runner_factory(client, folder_id: str):
        factory_calls.append((client, folder_id))
        return FakeGeneratedAgentRunner()

    service = AIInteractionService(
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
    service = AIInteractionService(
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
    service = AIInteractionService(
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

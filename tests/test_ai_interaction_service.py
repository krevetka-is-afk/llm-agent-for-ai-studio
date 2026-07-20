import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_interaction_service import (
    AIInteractionService,
    Attachment,
    InteractionRequest,
    MAX_ATTACHMENTS_PER_REQUEST,
    UploadValidationError,
)
from config import (
    AIServiceConfig,
    ConnectionConfig,
    ModelConfig,
    PathConfig,
    SessionDBConfig,
)
from context import AIStudioCredentials, ConversationOptions, ConversationState
from result_assembly import IndexedFileResult, VectorIndexResultPart


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
                    "arguments": (
                        '{"file_ids":["file-first"],"vector_store_name":"knowledge"}'
                    ),
                }
            ),
        )
        yield SimpleNamespace(
            type="run_item_stream_event",
            name="tool_output",
            item=SimpleNamespace(
                raw_item={"call_id": "call-index"},
                output="index-1",
            ),
        )


class FailingFakeAgent(FakeAgent):
    async def respond(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("agent failed")
        yield


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

    assert result.parts == (
        VectorIndexResultPart(
            index_name="knowledge",
            index_id="index-1",
            files=(IndexedFileResult("first.pdf", "file-first"),),
            expires_after_days=1,
        ),
    )
    assert rag.calls[0]["context"].allowed_file_ids == frozenset({"file-first"})


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
        "Files are already uploaded to AI Studio: first.pdf (file_id: file-first); "
        "second.pdf (file_id: file-second). Create the requested vector index using "
        "these file_ids now. Do not ask the user to upload the files again. "
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
    assert "file_id: file-first.pdf" in rag.calls[0]["message"]
    assert "file_id: file-second.pdf" in rag.calls[0]["message"]
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

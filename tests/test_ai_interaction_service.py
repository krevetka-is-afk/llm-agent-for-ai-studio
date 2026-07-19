import asyncio
from pathlib import Path
from types import SimpleNamespace

from ai_interaction_service import AIInteractionService, Attachment, InteractionRequest
from config import AIServiceConfig, ConnectionConfig, ModelConfig, PathConfig, SessionDBConfig
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
                        '{"file_ids":["file-first"],'
                        '"vector_store_name":"knowledge"}'
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
                credentials=AIStudioCredentials(api_key="AQAAAA-key", folder_id="folder"),
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
    assert (service.user_files_dir("web-connection") / attachment.filename).read_bytes() == b"data"


def test_service_builds_a_single_request_for_multiple_uploaded_files(tmp_path: Path) -> None:
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
                credentials=AIStudioCredentials(api_key="AQAAAA-key", folder_id="folder"),
                conversation_state=ConversationState(),
                user_files_dir=files_dir,
                attachments=(Attachment(filename="first.pdf"), Attachment(filename="second.pdf")),
            )
        )
    )

    assert uploaded == ["first.pdf", "second.pdf"]
    assert "file_id: file-first.pdf" in rag.calls[0]["message"]
    assert "file_id: file-second.pdf" in rag.calls[0]["message"]

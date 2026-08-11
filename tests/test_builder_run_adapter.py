import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_studio_agent_builder.application.builder_state import ConversationState
from ai_studio_agent_builder.application.dto import AIStudioCredentials
from ai_studio_agent_builder.application.interaction import Attachment
from ai_studio_agent_builder.application.ports.builder_run import BuilderRunRequest
from ai_studio_agent_builder.builder.agents.run_adapter import BuilderAgentsRunAdapter
from ai_studio_agent_builder.domain.routing import ConversationOptions


class _Files:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, file_id: str) -> None:
        self.deleted.append(file_id)


class _VectorStores:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, vector_store_id: str) -> None:
        self.deleted.append(vector_store_id)


class _FailingAgent:
    async def respond(self, **_kwargs):
        if False:
            yield None
        raise RuntimeError("synthetic agent failure")


def test_failed_builder_run_deletes_every_newly_uploaded_file(tmp_path: Path) -> None:
    client = SimpleNamespace(files=_Files(), vector_stores=_VectorStores())
    upload_count = 0

    def upload(_client, _base_dir: Path, filename: str) -> str:
        nonlocal upload_count
        upload_count += 1
        return f"file-{upload_count}-{filename}"

    agent = _FailingAgent()
    adapter = BuilderAgentsRunAdapter(
        coordinator_agent=agent,
        rag_agent=agent,
        one_prompt_agent=agent,
        sync_client_factory=lambda _credentials: client,
        async_client_factory=lambda _credentials: SimpleNamespace(),
        file_uploader=upload,
    )
    (tmp_path / "one.txt").write_text("one", encoding="utf-8")
    (tmp_path / "two.txt").write_text("two", encoding="utf-8")
    request = BuilderRunRequest(
        user_id="user-1",
        request_id="request-1",
        text="build a RAG agent",
        credentials=AIStudioCredentials(api_key="test-key", folder_id="folder"),
        conversation_state=ConversationState(ConversationOptions.RAG),
        user_files_dir=tmp_path,
        attachments=(Attachment("one.txt"), Attachment("two.txt")),
    )

    with pytest.raises(RuntimeError, match="synthetic agent failure"):
        asyncio.run(adapter.run(request))

    assert client.files.deleted == ["file-2-two.txt", "file-1-one.txt"]

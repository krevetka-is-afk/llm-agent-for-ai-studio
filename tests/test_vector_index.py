import json
from types import SimpleNamespace
from typing import Any

import pytest

from ai_studio_agent_builder.application.builder_state import (
    ConversationOptions,
    ConversationState,
)
from ai_studio_agent_builder.builder.agents.tools import vector_index


class FakeVectorStores:
    def __init__(self, statuses: list[str]) -> None:
        self._statuses = statuses
        self.retrieve_calls: list[str] = []
        self.create_kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.create_kwargs = kwargs
        return SimpleNamespace(id="vs_123")

    def retrieve(self, vector_store_id: str) -> SimpleNamespace:
        self.retrieve_calls.append(vector_store_id)
        if self._statuses:
            status = self._statuses.pop(0)
        else:
            status = "in_progress"
        return SimpleNamespace(status=status)


class FakeClient:
    def __init__(self, statuses: list[str] | None = None) -> None:
        self.vector_stores = FakeVectorStores(statuses or [])


def make_ctx(
    client: FakeClient, state: ConversationState | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(
            user_id="user_1",
            request_id="request_1",
            client=client,
            state=state,
            allowed_file_ids=frozenset({"file_1", "file_2"}),
            filenames_by_file_id={
                "file_1": "guide.pdf",
                "file_2": "faq.txt",
            },
        )
    )


def test_create_search_index_returns_id_when_completed() -> None:
    client = FakeClient(["in_progress", "completed"])
    state = ConversationState(ConversationOptions.RAG)
    sleeps: list[float] = []

    result = vector_index._create_search_index_impl(
        make_ctx(client, state),
        ["file_1", "file_2"],
        "knowledge",
        sleep=sleeps.append,
    )

    assert result == "vs_123"
    assert client.vector_stores.create_kwargs is not None
    assert client.vector_stores.create_kwargs["file_ids"] == ["file_1", "file_2"]
    assert client.vector_stores.create_kwargs["name"] == "knowledge"
    assert client.vector_stores.retrieve_calls == ["vs_123", "vs_123"]
    assert sleeps == [3.0]
    assert state.agent_specification is not None
    assert state.agent_specification.parameters["index_id"] == "vs_123"
    assert [
        source.source_id for source in state.agent_specification.knowledge_sources
    ] == [
        "file_1",
        "file_2",
    ]
    assert [source.title for source in state.agent_specification.knowledge_sources] == [
        "guide.pdf",
        "faq.txt",
    ]

    sleeps.clear()
    vector_index._wait_for_vector_store_completed(
        client=FakeClient(["completed"]),
        vector_store_id="vs_done",
        tool_logger=vector_index.logger,
        sleep=sleeps.append,
    )
    assert sleeps == []


@pytest.mark.parametrize("status", ["failed", "cancelled", "expired"])
def test_known_terminal_failures_raise_typed_error(status: str) -> None:
    client = FakeClient([status])

    with pytest.raises(vector_index.VectorIndexTerminalStatusError) as exc_info:
        vector_index._wait_for_vector_store_completed(
            client=client,
            vector_store_id="vs_bad",
            tool_logger=vector_index.logger,
            sleep=lambda _: None,
        )

    assert exc_info.value.vector_store_id == "vs_bad"
    assert exc_info.value.status == status


def test_perpetual_in_progress_times_out_without_real_sleep() -> None:
    client = FakeClient(["in_progress", "in_progress", "in_progress"])
    sleeps: list[float] = []

    with pytest.raises(vector_index.VectorIndexPollingTimeoutError) as exc_info:
        vector_index._wait_for_vector_store_completed(
            client=client,
            vector_store_id="vs_slow",
            tool_logger=vector_index.logger,
            sleep=sleeps.append,
            monotonic=lambda: 0.0,
            max_attempts=3,
        )

    assert exc_info.value.vector_store_id == "vs_slow"
    assert exc_info.value.last_status == "in_progress"
    assert exc_info.value.attempts == 3
    assert sleeps == [3.0, 3.0]


def test_unknown_status_raises_bounded_typed_error() -> None:
    client = FakeClient(["migrating"])

    with pytest.raises(vector_index.VectorIndexUnknownStatusError) as exc_info:
        vector_index._wait_for_vector_store_completed(
            client=client,
            vector_store_id="vs_unknown",
            tool_logger=vector_index.logger,
            sleep=lambda _: None,
        )

    assert exc_info.value.vector_store_id == "vs_unknown"
    assert exc_info.value.status == "migrating"
    assert exc_info.value.attempt == 1
    assert client.vector_stores.retrieve_calls == ["vs_unknown"]


def test_tool_uses_only_server_managed_pending_files() -> None:
    client = FakeClient(["completed"])
    state = ConversationState(ConversationOptions.RAG)
    state.register_pending_files(
        {
            "file_1": "guide.pdf",
            "file_2": "faq.txt",
        }
    )

    output = json.loads(
        vector_index._create_search_index_for_context(
            make_ctx(client, state),
            "knowledge",
        )
    )

    assert output == {
        "status": "created",
        "index_id": "vs_123",
        "index_name": "knowledge",
        "file_ids": ["file_1", "file_2"],
    }
    assert client.vector_stores.create_kwargs is not None
    assert client.vector_stores.create_kwargs["file_ids"] == ["file_1", "file_2"]
    assert state.pending_file_ids == ()


def test_tool_returns_controlled_status_when_no_files_are_available() -> None:
    client = FakeClient()
    state = ConversationState(ConversationOptions.RAG)

    output = json.loads(
        vector_index._create_search_index_for_context(
            make_ctx(client, state),
            "knowledge",
        )
    )

    assert output["status"] == "needs_files"
    assert client.vector_stores.create_kwargs is None


def test_tool_reuses_attached_index_instead_of_recreating_it() -> None:
    client = FakeClient()
    state = ConversationState(ConversationOptions.RAG)
    state.attach_vector_index(
        index_id="vs_existing",
        index_name="knowledge",
        file_ids=("file_1",),
    )

    output = json.loads(
        vector_index._create_search_index_for_context(
            make_ctx(client, state),
            "knowledge",
        )
    )

    assert output == {
        "status": "exists",
        "index_id": "vs_existing",
        "index_name": "knowledge",
        "file_ids": ["file_1"],
    }
    assert client.vector_stores.create_kwargs is None


def test_tool_schema_does_not_expose_server_managed_file_ids() -> None:
    assert vector_index.create_search_index.params_json_schema["required"] == [
        "vector_store_name",
    ]
    assert (
        "file_ids"
        not in vector_index.create_search_index.params_json_schema["properties"]
    )

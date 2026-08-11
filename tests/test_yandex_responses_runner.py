import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from openai import NotFoundError

from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentProviderError,
    AgentProviderTimeoutError,
    VectorStoreUnavailableError,
)
from ai_studio_agent_builder.domain.runtime import ExecutableAgentConfig
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.responses_runner import (
    YandexResponsesAgentRunner,
)


class FakeResponses:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response or SimpleNamespace(
            id="resp-1",
            output_text="Answer",
            output=[],
            usage=None,
        )
        self.error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeVectorStores:
    def __init__(
        self,
        statuses: dict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.statuses = statuses or {}
        self.error = error
        self.retrieve_calls: list[str] = []

    def retrieve(self, vector_store_id: str):
        self.retrieve_calls.append(vector_store_id)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(status=self.statuses.get(vector_store_id, "completed"))


class FakeClient:
    def __init__(
        self,
        *,
        response=None,
        response_error: Exception | None = None,
        statuses: dict[str, str] | None = None,
        vector_error: Exception | None = None,
    ) -> None:
        self.responses = FakeResponses(response, response_error)
        self.vector_stores = FakeVectorStores(statuses, vector_error)


def _config(*, tools=()) -> ExecutableAgentConfig:
    return ExecutableAgentConfig(
        schema_version="1.0",
        model_name="gpt-oss-120b",
        instructions="Be concise.",
        tools=tools,
        temperature=0.2,
        max_output_tokens=500,
    )


def test_one_prompt_sends_exact_payload_without_tools() -> None:
    client = FakeClient()
    runner = YandexResponsesAgentRunner(client, folder_id="folder-1")

    preview = runner.run(_config(), "Hello")

    assert client.responses.calls == [
        {
            "model": "gpt://folder-1/gpt-oss-120b",
            "instructions": "Be concise.",
            "input": "Hello",
            "temperature": 0.2,
            "max_output_tokens": 500,
        }
    ]
    assert preview.response_id == "resp-1"
    assert preview.output_text == "Answer"


def test_web_search_sends_native_tool_without_preflight() -> None:
    client = FakeClient()
    runner = YandexResponsesAgentRunner(client, folder_id="folder-1")
    tool = {"type": "web_search", "search_context_size": "medium"}

    runner.run(_config(tools=(tool,)), "Latest news")

    assert client.responses.calls[0]["tools"] == [tool]
    assert client.vector_stores.retrieve_calls == []


def test_code_interpreter_sends_bound_files_without_vector_preflight() -> None:
    client = FakeClient()
    runner = YandexResponsesAgentRunner(client, folder_id="folder-1")
    tool = {
        "type": "code_interpreter",
        "container": {
            "type": "auto",
            "memory_limit": "1g",
            "network_policy": {"type": "disabled"},
            "file_ids": ["file-request-1"],
        },
    }

    runner.run(_config(tools=(tool,)), "Calculate the total")

    assert client.responses.calls[0]["tools"] == [tool]
    assert client.vector_stores.retrieve_calls == []


def test_file_search_preflights_vector_store_before_response() -> None:
    client = FakeClient(statuses={"vs-123": "completed"})
    runner = YandexResponsesAgentRunner(client, folder_id="folder-1")
    tool = {"type": "file_search", "vector_store_ids": ["vs-123"]}

    runner.run(_config(tools=(tool,)), "Question")

    assert client.vector_stores.retrieve_calls == ["vs-123"]
    assert client.responses.calls[0]["tools"] == [tool]


@pytest.mark.parametrize("status", ["in_progress", "expired", "failed", "cancelled"])
def test_file_search_stops_before_response_for_unavailable_store(status: str) -> None:
    client = FakeClient(statuses={"vs-123": status})
    runner = YandexResponsesAgentRunner(client, folder_id="folder-1")

    with pytest.raises(VectorStoreUnavailableError) as exc_info:
        runner.run(
            _config(tools=({"type": "file_search", "vector_store_ids": ["vs-123"]},)),
            "Question",
        )

    assert exc_info.value.status == status
    assert client.responses.calls == []


def test_file_search_normalizes_not_found() -> None:
    request = httpx.Request("GET", "https://example.test/vector_stores/vs-404")
    response = httpx.Response(404, request=request)
    client = FakeClient(
        vector_error=NotFoundError("secret provider body", response=response, body=None)
    )
    runner = YandexResponsesAgentRunner(client, folder_id="folder-1")

    with pytest.raises(VectorStoreUnavailableError) as exc_info:
        runner.run(
            _config(tools=({"type": "file_search", "vector_store_ids": ["vs-404"]},)),
            "Question",
        )

    assert exc_info.value.status == "not_found"
    assert "secret provider body" not in str(exc_info.value)
    assert client.responses.calls == []


def test_runner_extracts_usage_and_known_citations() -> None:
    response = {
        "id": "resp-2",
        "output_text": "Grounded answer",
        "usage": {
            "input_tokens": 12,
            "output_tokens": 7,
            "total_tokens": 19,
        },
        "output": [
            {
                "type": "code_interpreter_call",
                "container_id": "container-1",
                "status": "completed",
            },
            {
                "content": [
                    {
                        "annotations": [
                            {
                                "type": "url_citation",
                                "title": "Yandex docs",
                                "url": "https://example.test/docs",
                            },
                            {
                                "type": "file_citation",
                                "file_id": "file-1",
                                "filename": "guide.pdf",
                            },
                            {
                                "type": "container_file_citation",
                                "container_id": "container-1",
                                "file_id": "file-output-1",
                                "filename": "result.csv",
                            },
                            {"type": "future_annotation", "secret": "ignored"},
                        ]
                    }
                ]
            },
        ],
    }
    runner = YandexResponsesAgentRunner(FakeClient(response=response), folder_id="f")

    preview = runner.run(_config(), "Question")

    assert preview.input_tokens == 12
    assert preview.output_tokens == 7
    assert preview.total_tokens == 19
    assert [(citation.kind, citation.title) for citation in preview.citations] == [
        ("url", "Yandex docs"),
        ("file", "guide.pdf"),
    ]
    assert [
        (artifact.file_id, artifact.filename, artifact.container_id)
        for artifact in preview.generated_artifacts
    ] == [("file-output-1", "result.csv", "container-1")]
    assert preview.container_ids == ("container-1",)


def test_runner_ignores_unknown_annotation_shapes() -> None:
    response = SimpleNamespace(
        id="resp-3",
        output_text="Answer",
        output=[SimpleNamespace(content=[SimpleNamespace(annotations={"bad": True})])],
        usage=SimpleNamespace(input_tokens=None),
    )
    runner = YandexResponsesAgentRunner(FakeClient(response=response), folder_id="f")

    preview = runner.run(_config(), "Question")

    assert preview.citations == ()
    assert preview.input_tokens is None


def test_runner_normalizes_anonymized_code_interpreter_contract_fixture() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "code_interpreter"
        / "yandex_response_contract.json"
    )
    response = json.loads(fixture_path.read_text(encoding="utf-8"))
    runner = YandexResponsesAgentRunner(FakeClient(response=response), folder_id="f")

    preview = runner.run(_config(), "Question")

    assert preview.citations == ()
    assert preview.generated_artifacts[0].file_id == "<file_id>"
    assert preview.generated_artifacts[0].filename == "result.csv"
    assert preview.generated_artifacts[0].container_id == "<container_id>"
    assert preview.container_ids == ("<container_id>",)


def test_runner_normalizes_timeout_and_unknown_provider_errors() -> None:
    timeout_runner = YandexResponsesAgentRunner(
        FakeClient(response_error=TimeoutError("provider details")),
        folder_id="f",
    )
    with pytest.raises(AgentProviderTimeoutError) as timeout:
        timeout_runner.run(_config(), "Question")
    assert "provider details" not in str(timeout.value)

    error_runner = YandexResponsesAgentRunner(
        FakeClient(response_error=RuntimeError("api-key=secret")),
        folder_id="f",
    )
    with pytest.raises(AgentProviderError) as provider:
        error_runner.run(_config(), "Question")
    assert "secret" not in str(provider.value)

import asyncio
import csv
import io
import logging
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from openai.types import vector_store_create_params

from ai_studio_agent_builder.application.dto import AIStudioCredentials
from ai_studio_agent_builder.application.interaction import (
    AgentTestRequest,
    AgentTestResult,
    Attachment,
)
from ai_studio_agent_builder.application.interaction_facade import (
    AIInteractionService,
)
from ai_studio_agent_builder.builder.agents.tools.vector_index import (
    DEFAULT_CHUNKING_STRATEGY,
    _wait_for_vector_store_completed,
)
from ai_studio_agent_builder.composition import build_ai_interaction_service
from ai_studio_agent_builder.domain.specification import (
    KnowledgeSource,
    build_one_prompt_specification,
    build_rag_specification,
)
from ai_studio_agent_builder.config import (
    AIServiceConfig,
    AgentRuntimeConfig,
    ConnectionConfig,
    ModelConfig,
    PathConfig,
    SessionDBConfig,
)
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.client_factory import (
    get_api_key_client,
)
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.files_gateway import (
    YandexFileResourceGateway,
    upload_local_file,
)


pytestmark = [
    pytest.mark.yandex_ai_studio_e2e,
    pytest.mark.skipif(
        os.getenv("RUN_YANDEX_AI_STUDIO_E2E") != "1",
        reason="Set RUN_YANDEX_AI_STUDIO_E2E=1 to run credentialed E2E tests",
    ),
]


def _credentials() -> AIStudioCredentials:
    api_key = os.getenv("YC_AI_STUDIO_API_KEY")
    folder_id = os.getenv("YC_AI_STUDIO_FOLDER_ID")
    if not api_key or not folder_id:
        pytest.fail(
            "RUN_YANDEX_AI_STUDIO_E2E=1 requires YC_AI_STUDIO_API_KEY and "
            "YC_AI_STUDIO_FOLDER_ID"
        )
    return AIStudioCredentials(api_key=api_key, folder_id=folder_id)


def _service_config(tmp_path: Path) -> AIServiceConfig:
    model_name = os.getenv("YC_AI_STUDIO_MODEL", "gpt-oss-120b")
    base_url = os.getenv(
        "YC_AI_STUDIO_BASE_URL",
        "https://ai.api.cloud.yandex.net/v1",
    )
    session_db_path = tmp_path / "sessions.db"
    builder_model = ModelConfig(
        model_name=model_name,
        temperature=0.0,
        max_output_tokens=1000,
        base_url=base_url,
        sessions_db_path=session_db_path,
    )
    return AIServiceConfig(
        paths=PathConfig(uploaded_files_dir=tmp_path / "uploaded_files"),
        connection=ConnectionConfig(
            base_url=base_url,
            timeout=float(os.getenv("YC_AI_STUDIO_REQUEST_TIMEOUT_SECONDS", "90")),
        ),
        session_db_config=SessionDBConfig(path=session_db_path),
        rag_model=builder_model,
        one_prompt=builder_model,
        consultant=builder_model,
        generated_agent_runtime=AgentRuntimeConfig(
            model_name=model_name,
            temperature=0.0,
            max_output_tokens=1000,
        ),
    )


def test_generated_one_prompt_runs_through_responses_api(tmp_path: Path) -> None:
    asyncio.run(_run_one_prompt(tmp_path))


async def _run_one_prompt(tmp_path: Path) -> None:
    credentials = _credentials()
    service = build_ai_interaction_service(_service_config(tmp_path))
    specification = build_one_prompt_specification(
        purpose="Verify generated-agent runtime",
        instructions="Answer the user's request directly and concisely.",
        expected_result="A non-empty text response",
    )

    result = await _test_agent(
        service,
        credentials,
        specification.to_record(),
        "Reply with the exact phrase DAY2_ONE_PROMPT_OK.",
    )

    assert result.output_text.strip()
    _assert_no_credentials(result, credentials)


@pytest.mark.yandex_ai_studio_web_search_e2e
def test_generated_web_search_runs_with_native_tool(tmp_path: Path) -> None:
    asyncio.run(_run_web_search(tmp_path))


async def _run_web_search(tmp_path: Path) -> None:
    credentials = _credentials()
    service = build_ai_interaction_service(_service_config(tmp_path))
    specification = build_one_prompt_specification(
        purpose="Answer questions using current public information",
        instructions=(
            "Use web search before answering and mention the official source."
        ),
        expected_result="A concise source-grounded answer",
        web_search=True,
    )

    result = await _test_agent(
        service,
        credentials,
        specification.to_record(),
        "What is Yandex Cloud AI Studio? Answer in one sentence.",
    )

    assert result.output_text.strip()
    _assert_no_credentials(result, credentials)


def test_generated_rag_runs_with_file_search(tmp_path: Path) -> None:
    asyncio.run(_run_rag(tmp_path))


async def _run_rag(tmp_path: Path) -> None:
    credentials = _credentials()
    config = _service_config(tmp_path)
    service = build_ai_interaction_service(config)
    client = get_api_key_client(credentials, config.connection)
    source_dir = tmp_path / "rag-source"
    source_dir.mkdir()
    source_path = source_dir / "verification.txt"
    source_path.write_text(
        "The generated-agent runtime verification phrase is DAY2_FILE_SEARCH_OK.",
        encoding="utf-8",
    )
    file_id: str | None = None
    vector_store_id: str | None = None
    try:
        file_id = await asyncio.to_thread(
            upload_local_file,
            client,
            source_dir,
            source_path.name,
        )
        vector_store = await asyncio.to_thread(
            client.vector_stores.create,
            name=f"generated-agent-runtime-e2e-{uuid4().hex[:12]}",
            expires_after=vector_store_create_params.ExpiresAfter(
                anchor="last_active_at",
                days=1,
            ),
            chunking_strategy=DEFAULT_CHUNKING_STRATEGY,
            file_ids=[file_id],
        )
        vector_store_id = vector_store.id
        await asyncio.to_thread(
            _wait_for_vector_store_completed,
            client=client,
            vector_store_id=vector_store_id,
            tool_logger=logging.getLogger(__name__),
        )
        specification = build_rag_specification(
            purpose="Answer questions from the temporary verification source",
            instructions="Always search the connected source before answering.",
            expected_result="The exact verification phrase from the source",
            index_id=vector_store_id,
            index_name="runtime-e2e",
            knowledge_sources=(
                KnowledgeSource(
                    source_id=file_id,
                    title=source_path.name,
                    kind="uploaded_file",
                    reference=file_id,
                ),
            ),
        )

        result = await _test_agent(
            service,
            credentials,
            specification.to_record(),
            "What is the generated-agent runtime verification phrase?",
        )

        assert "DAY2_FILE_SEARCH_OK" in result.output_text
        _assert_no_credentials(result, credentials)
    finally:
        if vector_store_id is not None:
            await asyncio.to_thread(client.vector_stores.delete, vector_store_id)
        if file_id is not None:
            await asyncio.to_thread(client.files.delete, file_id)


def test_generated_code_interpreter_runs_service_file_lifecycle(
    tmp_path: Path,
) -> None:
    asyncio.run(_run_code_interpreter(tmp_path))


async def _run_code_interpreter(tmp_path: Path) -> None:
    credentials = _credentials()
    config = _service_config(tmp_path)
    client = get_api_key_client(credentials, config.connection)
    tracked_files = _TrackedFileResources(YandexFileResourceGateway(client))
    service = build_ai_interaction_service(
        config,
        file_resource_gateway_factory=_TrackedFileResourceGatewayFactory(tracked_files),
    )
    user_id = f"code-interpreter-runtime-e2e-{uuid4().hex}"
    context = service.save_attachment(
        user_id,
        "context.txt",
        b"Multiply the CSV sum by 2.\n",
    )
    numbers = service.save_attachment(
        user_id,
        "numbers.csv",
        b"label,value\nalpha,10\nbeta,15\ngamma,25\n",
    )
    specification = build_one_prompt_specification(
        purpose="Verify the generated Code Interpreter runtime",
        instructions=(
            "Always use Code Interpreter to read attached files, calculate the "
            "answer, and create the requested output file."
        ),
        expected_result="A marker and a cited result.csv artifact",
        code_interpreter=True,
    )
    runtime_json = service.prepare_agent_runtime(specification.to_record()).to_json()
    assert "file_ids" not in runtime_json

    try:
        result = await _test_agent(
            service,
            credentials,
            specification.to_record(),
            (
                "Read both attached files. Create result.csv with columns "
                "metric,value and rows sum, multiplier, result. Reply with "
                "SERVICE_CODE_INTERPRETER_OK and cite result.csv."
            ),
            user_id=user_id,
            attachments=(context, numbers),
        )

        assert "SERVICE_CODE_INTERPRETER_OK" in result.output_text
        assert result.generated_file_warnings == ()
        generated = [
            artifact
            for artifact in result.generated_files
            if artifact.display_name == "result.csv"
        ]
        assert len(generated) == 1
        assert generated[0].mime_type == "text/csv"
        payload = service.read_generated_file(user_id, generated[0].local_name)
        rows = {
            row["metric"]: float(row["value"])
            for row in csv.DictReader(io.StringIO(payload.decode("utf-8")))
        }
        assert rows == {"sum": 50.0, "multiplier": 2.0, "result": 100.0}

        assert tracked_files.uploaded_input_ids
        assert tracked_files.downloaded_output_ids
        assert tracked_files.uploaded_input_ids <= tracked_files.deleted_file_ids
        assert tracked_files.downloaded_output_ids <= tracked_files.deleted_file_ids
        assert tracked_files.deleted_container_ids
        serialized_result = repr(result)
        for remote_id in (
            tracked_files.uploaded_input_ids
            | tracked_files.downloaded_output_ids
            | tracked_files.deleted_container_ids
        ):
            assert remote_id not in serialized_result
        _assert_no_credentials(result, credentials)
    finally:
        await service.reset_conversation(user_id)


async def _test_agent(
    service: AIInteractionService,
    credentials: AIStudioCredentials,
    specification_record: dict,
    user_input: str,
    *,
    user_id: str | None = None,
    attachments: tuple[Attachment, ...] = (),
) -> AgentTestResult:
    runtime_json = service.prepare_agent_runtime(specification_record).to_json()
    assert credentials.api_key not in runtime_json
    assert credentials.folder_id not in runtime_json
    return await asyncio.wait_for(
        service.test_agent_specification(
            AgentTestRequest(
                user_id=user_id or f"runtime-e2e-{uuid4().hex}",
                credentials=credentials,
                specification_record=specification_record,
                user_input=user_input,
                attachments=attachments,
            )
        ),
        timeout=float(os.getenv("YC_AI_STUDIO_E2E_TIMEOUT_SECONDS", "420")),
    )


def _assert_no_credentials(
    result: AgentTestResult,
    credentials: AIStudioCredentials,
) -> None:
    serialized_result = repr(result)
    assert credentials.api_key not in serialized_result
    assert credentials.folder_id not in serialized_result


class _TrackedFileResources:
    def __init__(self, delegate: YandexFileResourceGateway) -> None:
        self._delegate = delegate
        self.uploaded_input_ids: set[str] = set()
        self.downloaded_output_ids: set[str] = set()
        self.deleted_file_ids: set[str] = set()
        self.deleted_container_ids: set[str] = set()

    def upload_user_file(self, base_dir: Path, filename: str) -> str:
        file_id = self._delegate.upload_user_file(base_dir, filename)
        self.uploaded_input_ids.add(file_id)
        return file_id

    def iter_file_bytes(
        self,
        file_id: str,
        *,
        chunk_size: int,
    ) -> Iterator[bytes]:
        self.downloaded_output_ids.add(file_id)
        yield from self._delegate.iter_file_bytes(file_id, chunk_size=chunk_size)

    def delete_file(self, file_id: str) -> None:
        self._delegate.delete_file(file_id)
        self.deleted_file_ids.add(file_id)

    def delete_container(self, container_id: str) -> None:
        self._delegate.delete_container(container_id)
        self.deleted_container_ids.add(container_id)


class _TrackedFileResourceGatewayFactory:
    def __init__(self, gateway: _TrackedFileResources) -> None:
        self._gateway = gateway

    def create(self, credentials: AIStudioCredentials) -> _TrackedFileResources:
        del credentials
        return self._gateway

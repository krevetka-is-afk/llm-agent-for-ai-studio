import asyncio
import logging
import os
from pathlib import Path
from uuid import uuid4

import pytest
from openai.types import vector_store_create_params

from agent_specification import (
    KnowledgeSource,
    build_one_prompt_specification,
    build_rag_specification,
)
from ai_interaction_service import (
    AIInteractionService,
    AgentTestRequest,
    AgentTestResult,
)
from ai_studio_agent_builder.config import (
    AIServiceConfig,
    AgentRuntimeConfig,
    ConnectionConfig,
    ModelConfig,
    PathConfig,
    SessionDBConfig,
)
from context import AIStudioCredentials, get_api_key_client
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.files_gateway import (
    upload_local_file,
)
from custom_agents.tools.vector_index import (
    DEFAULT_CHUNKING_STRATEGY,
    _wait_for_vector_store_completed,
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
    service = AIInteractionService(_service_config(tmp_path))
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
    service = AIInteractionService(_service_config(tmp_path))
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
    service = AIInteractionService(config)
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


async def _test_agent(
    service: AIInteractionService,
    credentials: AIStudioCredentials,
    specification_record: dict,
    user_input: str,
) -> AgentTestResult:
    runtime_json = service.prepare_agent_runtime(specification_record).to_json()
    assert credentials.api_key not in runtime_json
    assert credentials.folder_id not in runtime_json
    return await asyncio.wait_for(
        service.test_agent_specification(
            AgentTestRequest(
                user_id=f"runtime-e2e-{uuid4().hex}",
                credentials=credentials,
                specification_record=specification_record,
                user_input=user_input,
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

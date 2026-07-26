import asyncio
import os
import shutil
import warnings
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

import ai_interaction_service as interaction_module
from ai_interaction_service import AIInteractionService, InteractionRequest
from config import (
    AgentRuntimeConfig,
    AIServiceConfig,
    ConnectionConfig,
    ModelConfig,
    PathConfig,
    SessionDBConfig,
)
from context import (
    AIStudioCredentials,
    ConversationOptions,
    ConversationState,
    get_api_key_client,
)
from result_assembly import VectorIndexResultPart

pytestmark = [
    pytest.mark.yandex_ai_studio_e2e,
    pytest.mark.skipif(
        os.getenv("RUN_YANDEX_AI_STUDIO_E2E") != "1",
        reason="Set RUN_YANDEX_AI_STUDIO_E2E=1 to run credentialed E2E tests",
    ),
]


def _required_e2e_env() -> AIStudioCredentials:
    api_key = os.getenv("YC_AI_STUDIO_API_KEY")
    folder_id = os.getenv("YC_AI_STUDIO_FOLDER_ID")
    if not api_key or not folder_id:
        pytest.fail(
            "RUN_YANDEX_AI_STUDIO_E2E=1 requires YC_AI_STUDIO_API_KEY and "
            "YC_AI_STUDIO_FOLDER_ID"
        )
    return AIStudioCredentials(api_key=api_key, folder_id=folder_id)


def _service_config(tmp_path: Path) -> AIServiceConfig:
    model = ModelConfig(
        model_name=os.getenv("YC_AI_STUDIO_MODEL", "gpt-oss-120b"),
        temperature=0.0,
        max_output_tokens=1000,
        base_url=os.getenv(
            "YC_AI_STUDIO_BASE_URL", "https://ai.api.cloud.yandex.net/v1"
        ),
        sessions_db_path=tmp_path / "sessions.db",
    )
    return AIServiceConfig(
        paths=PathConfig(uploaded_files_dir=tmp_path / "uploaded_files"),
        connection=ConnectionConfig(
            base_url=model.base_url,
            timeout=float(os.getenv("YC_AI_STUDIO_REQUEST_TIMEOUT_SECONDS", "90")),
        ),
        session_db_config=SessionDBConfig(path=tmp_path / "sessions.db"),
        rag_model=model,
        one_prompt=model,
        consultant=model,
        generated_agent_runtime=AgentRuntimeConfig(
            model_name=model.model_name,
            temperature=0.0,
            max_output_tokens=1000,
        ),
    )


def _warn_cleanup(resource: str) -> None:
    warnings.warn(
        f"Credentialed E2E cleanup could not remove {resource}",
        RuntimeWarning,
        stacklevel=2,
    )


async def _cleanup(
    service: AIInteractionService,
    client: Any | None,
    user_id: str,
    index_name: str,
    vector_store_ids: set[str],
    file_ids: list[str],
    tmp_path: Path,
    *,
    keep_remote: bool,
) -> None:
    if not keep_remote and client is not None and not vector_store_ids:
        try:
            vector_stores = await asyncio.to_thread(client.vector_stores.list)
            vector_store_ids.update(
                store.id
                for store in getattr(vector_stores, "data", ())
                if getattr(store, "name", None) == index_name
                and isinstance(getattr(store, "id", None), str)
            )
        except Exception:
            _warn_cleanup("vector store lookup")
    if not keep_remote and client is not None:
        for remote_vector_store_id in vector_store_ids:
            try:
                await asyncio.to_thread(
                    client.vector_stores.delete, remote_vector_store_id
                )
            except Exception:
                _warn_cleanup("vector store")
    if not keep_remote and client is not None:
        for _file_id in file_ids:
            try:
                await asyncio.to_thread(client.files.delete, _file_id)
            except Exception:
                _warn_cleanup("uploaded file")
    try:
        await service.reset_conversation(user_id)
    except Exception:
        _warn_cleanup("local session")
    shutil.rmtree(tmp_path / "uploaded_files", ignore_errors=True)


def test_yandex_ai_studio_rag_creates_structured_vector_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_run_yandex_ai_studio_rag_e2e(tmp_path, monkeypatch))


async def _run_yandex_ai_studio_rag_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = _required_e2e_env()
    config = _service_config(tmp_path)
    service = AIInteractionService(config)
    resource_suffix = uuid4().hex[:12]
    user_id = f"e2e-yandex-ai-studio-rag-{resource_suffix}"
    index_name = f"codex-e2e-{resource_suffix}"
    user_dir = service.user_files_dir(user_id)
    local_filename = "tiny-rag-source.txt"
    attachment = service.save_attachment(
        user_id,
        local_filename,
        (
            "Project codename: Day 2 RAG credentialed E2E.\n"
            "The expected verification phrase is VECTOR_INDEX_RESULT_PART_OK.\n"
        ).encode(),
    )

    client = get_api_key_client(credentials, config.connection)
    uploaded_file_ids: list[str] = []
    created_vector_store_ids: set[str] = set()
    real_upload_local_file = interaction_module.upload_local_file
    real_vector_store_create = client.vector_stores.create

    def _capture_upload(*args: Any, **kwargs: Any) -> str:
        file_id = real_upload_local_file(*args, **kwargs)
        uploaded_file_ids.append(file_id)
        return file_id

    def _capture_vector_store(*args: Any, **kwargs: Any) -> Any:
        vector_store = real_vector_store_create(*args, **kwargs)
        if isinstance(getattr(vector_store, "id", None), str):
            created_vector_store_ids.add(vector_store.id)
        return vector_store

    monkeypatch.setattr(
        interaction_module,
        "get_api_key_client",
        lambda _credentials, _connection: client,
    )
    monkeypatch.setattr(interaction_module, "upload_local_file", _capture_upload)
    monkeypatch.setattr(client.vector_stores, "create", _capture_vector_store)
    try:
        state = ConversationState()
        state.update_state(ConversationOptions.RAG)

        result = await asyncio.wait_for(
            service.interact(
                InteractionRequest(
                    user_id=user_id,
                    text=(
                        f"Create a vector index named {index_name} from the uploaded "
                        "file and generate the system prompt. Use the files managed "
                        "by the service; do not ask for another upload or file IDs."
                    ),
                    credentials=credentials,
                    conversation_state=state,
                    user_files_dir=user_dir,
                    attachments=(attachment,),
                ),
            ),
            timeout=float(os.getenv("YC_AI_STUDIO_E2E_TIMEOUT_SECONDS", "420")),
        )

        assert result.selected_agent is ConversationOptions.RAG
        assert result.responded_by is ConversationOptions.RAG
        assert result.next_state is ConversationOptions.RAG
        vector_parts = [
            part for part in result.parts if isinstance(part, VectorIndexResultPart)
        ]
        assert len(vector_parts) == 1
        vector_part = vector_parts[0]
        assert vector_part.index_name == index_name
        assert vector_part.index_id
        assert vector_part.index_id in created_vector_store_ids
        assert vector_part.expires_after_days == 1
        assert len(uploaded_file_ids) == 1
        assert tuple(file.file_id for file in vector_part.files) == (
            uploaded_file_ids[0],
        )
        assert tuple(file.filename for file in vector_part.files) == (local_filename,)
        assert vector_part.index_id in result.text
        assert index_name in result.text
        assert credentials.api_key not in result.text
        assert credentials.folder_id not in result.text
        assert credentials.api_key not in repr(result.parts)
        assert credentials.folder_id not in repr(result.parts)
    finally:
        await _cleanup(
            service,
            client,
            user_id,
            index_name,
            created_vector_store_ids,
            uploaded_file_ids,
            tmp_path,
            keep_remote=os.getenv("YC_AI_STUDIO_E2E_KEEP_REMOTE") == "1",
        )

import io
import json
from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
import zipfile

from ai_studio_agent_builder.config import AgentRuntimeConfig
from ai_studio_agent_builder.presentation.streamlit import user_guidance
from ai_studio_agent_builder.presentation.streamlit.developer_bundle import (
    build_developer_bundle,
)
from ai_studio_agent_builder.domain.runtime import compile_agent_specification
from ai_studio_agent_builder.domain.specification import (
    AgentSpecification,
    KnowledgeSource,
    build_one_prompt_specification,
    build_rag_specification,
)
from ai_studio_agent_builder.domain.specification_codec import (
    load_agent_specification,
)

EXPECTED_FILES = {
    ".env.example",
    "README.md",
    "agent-specification.json",
    "example.py",
    "responses-agent-config.json",
}
RUNTIME = AgentRuntimeConfig(
    model_name="gpt-oss-120b",
    temperature=0.5,
    max_output_tokens=1000,
)
TEST_API_KEY = "AQAAAA-test-developer-bundle-secret"
TEST_FOLDER_ID = "test-developer-bundle-folder"
CODE_INTERPRETER_EXAMPLE_DIR = (
    Path(__file__).parents[1] / "examples" / "code-interpreter"
)


def _one_prompt_specification() -> AgentSpecification:
    return build_one_prompt_specification(
        purpose="Помогать пользователю находить актуальные сведения",
        instructions="Перед ответом выполняй веб-поиск.",
        expected_result="Краткий ответ со ссылками на источники",
        web_search=True,
    )


def _rag_specification() -> AgentSpecification:
    return build_rag_specification(
        purpose="Отвечать на вопросы по справочнику",
        instructions="Сначала найди релевантные фрагменты.",
        expected_result="Ответ, основанный на справочнике",
        index_id="vs-test-123",
        index_name="handbook",
        knowledge_sources=(
            KnowledgeSource(
                source_id="file-test-1",
                title="handbook.pdf",
                kind="uploaded_file",
                reference="file-test-1",
            ),
        ),
    )


def _code_interpreter_specification() -> AgentSpecification:
    return build_one_prompt_specification(
        purpose="Анализировать пользовательские таблицы",
        instructions="Используй Code Interpreter для вычислений и файлов.",
        expected_result="Ответ и созданный файл с результатом",
        code_interpreter=True,
    )


def _bundle_for(
    specification: AgentSpecification,
) -> tuple[bytes, str, dict[str, object]]:
    runtime_json = compile_agent_specification(
        specification,
        runtime=RUNTIME,
    ).to_json()
    specification_record = specification.to_record()
    return (
        build_developer_bundle(specification_record, runtime_json),
        runtime_json,
        specification_record,
    )


def test_developer_bundle_contains_runnable_secret_free_handoff(
    monkeypatch,
) -> None:
    monkeypatch.setenv("YC_AI_STUDIO_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("YC_AI_STUDIO_FOLDER_ID", TEST_FOLDER_ID)
    bundle, runtime_json, specification = _bundle_for(_one_prompt_specification())

    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert set(archive.namelist()) == EXPECTED_FILES
        assert archive.testzip() is None
        assert all(
            item.compress_type == zipfile.ZIP_DEFLATED for item in archive.infolist()
        )
        assert archive.read("responses-agent-config.json").decode() == runtime_json
        assert json.loads(archive.read("agent-specification.json")) == specification

        example = archive.read("example.py").decode()
        compile(example, "example.py", "exec")
        assert "client.responses.create" in example
        assert 'purpose="user_data"' in example
        assert "with_streaming_response.content" in example
        assert "_cleanup_remote_resources" in example

        readme = archive.read("README.md").decode()
        assert "### Bash (Linux, macOS, Git Bash)" in readme
        assert "### Windows PowerShell" in readme
        assert "### Windows Command Prompt (CMD)" in readme
        assert ".venv/bin/python example.py" in readme
        assert r".\.venv\Scripts\python.exe example.py" in readme
        assert r".venv\Scripts\python.exe example.py" in readme
        assert "example.py --file data.csv --file instructions.txt" in readme
        assert "provider TTL 20 минут" in readme

        env_example = archive.read(".env.example").decode()
        assert env_example == (
            "YC_AI_STUDIO_API_KEY=replace_with_api_key\n"
            "YC_AI_STUDIO_FOLDER_ID=replace_with_folder_id\n"
        )

        combined_text = "\n".join(
            archive.read(filename).decode() for filename in archive.namelist()
        )
        assert TEST_API_KEY not in combined_text
        assert TEST_FOLDER_ID not in combined_text


def test_rag_bundle_example_sends_compiled_request_without_network(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    bundle, runtime_json, specification = _bundle_for(_rag_specification())
    captured: dict[str, object] = {}

    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert archive.testzip() is None
        archive.extractall(tmp_path)

    class FakeResponses:
        def create(self, **request):
            captured["request"] = request
            return SimpleNamespace(output_text="stubbed-agent-answer")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = FakeResponses()

    openai_module = ModuleType("openai")
    setattr(openai_module, "OpenAI", FakeOpenAI)
    dotenv_module = ModuleType("dotenv")
    setattr(dotenv_module, "load_dotenv", lambda: None)

    monkeypatch.setitem(sys.modules, "openai", openai_module)
    monkeypatch.setitem(sys.modules, "dotenv", dotenv_module)
    monkeypatch.setenv("YC_AI_STUDIO_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("YC_AI_STUDIO_FOLDER_ID", TEST_FOLDER_ID)
    monkeypatch.setattr(sys, "argv", ["example.py"])
    monkeypatch.setattr("builtins.input", lambda _: "Что находится в справочнике?")
    monkeypatch.chdir(tmp_path)

    runpy.run_path(str(tmp_path / "example.py"), run_name="__main__")

    assert capsys.readouterr().out.strip() == "stubbed-agent-answer"
    assert captured["client"] == {
        "api_key": TEST_API_KEY,
        "project": TEST_FOLDER_ID,
        "base_url": "https://ai.api.cloud.yandex.net/v1",
        "default_headers": {"Authorization": f"Api-Key {TEST_API_KEY}"},
    }
    runtime = json.loads(runtime_json)
    assert captured["request"] == {
        "model": f"gpt://{TEST_FOLDER_ID}/gpt-oss-120b",
        "instructions": runtime["instructions"],
        "input": "Что находится в справочнике?",
        "temperature": 0.5,
        "max_output_tokens": 1000,
        "tools": [
            {
                "type": "file_search",
                "vector_store_ids": ["vs-test-123"],
            }
        ],
    }
    assert (
        json.loads((tmp_path / "agent-specification.json").read_text(encoding="utf-8"))
        == specification
    )


def test_code_interpreter_bundle_example_scopes_files_downloads_and_cleans_up(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    bundle, runtime_json, _ = _bundle_for(_code_interpreter_specification())
    captured: dict[str, Any] = {
        "deleted_files": [],
        "deleted_containers": [],
        "deleted_responses": [],
        "uploads": [],
    }
    input_path = tmp_path / "numbers.csv"
    input_payload = b"value\n10\n20\n"
    output_payload = b"metric,value\nsum,30\n"
    input_path.write_bytes(input_payload)

    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert archive.testzip() is None
        archive.extractall(tmp_path)

    runtime_path = tmp_path / "responses-agent-config.json"
    runtime_before = runtime_path.read_text(encoding="utf-8")

    class FakeStreamingResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def iter_bytes(self, *, chunk_size):
            captured["chunk_size"] = chunk_size
            yield output_payload[:8]
            yield output_payload[8:]

    class FakeStreamingFiles:
        def content(self, file_id):
            captured["downloaded_file_id"] = file_id
            return FakeStreamingResponse()

    class FakeFiles:
        with_streaming_response = FakeStreamingFiles()

        def create(self, *, file, purpose, expires_after):
            captured["uploads"].append((file.name, file.read(), purpose))
            captured["upload_expiration"] = expires_after
            return SimpleNamespace(id="input-request-file-id")

        def delete(self, file_id):
            captured["deleted_files"].append(file_id)

    class FakeContainers:
        def delete(self, container_id):
            captured["deleted_containers"].append(container_id)

    class FakeResponses:
        def create(self, **request):
            captured["request"] = request
            return SimpleNamespace(
                id="response-request-id",
                output_text="Файл рассчитан",
                output=[
                    SimpleNamespace(
                        type="code_interpreter_call",
                        container_id="container-request-id",
                    ),
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(
                                annotations=[
                                    SimpleNamespace(
                                        type="container_file_citation",
                                        file_id="output-request-file-id",
                                        filename="result.csv",
                                        container_id="container-request-id",
                                    )
                                ]
                            )
                        ],
                    ),
                ],
            )

        def delete(self, response_id):
            captured["deleted_responses"].append(response_id)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.files = FakeFiles()
            self.containers = FakeContainers()
            self.responses = FakeResponses()

    openai_module = ModuleType("openai")
    setattr(openai_module, "OpenAI", FakeOpenAI)
    dotenv_module = ModuleType("dotenv")
    setattr(dotenv_module, "load_dotenv", lambda: None)

    monkeypatch.setitem(sys.modules, "openai", openai_module)
    monkeypatch.setitem(sys.modules, "dotenv", dotenv_module)
    monkeypatch.setenv("YC_AI_STUDIO_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("YC_AI_STUDIO_FOLDER_ID", TEST_FOLDER_ID)
    monkeypatch.setattr(
        sys,
        "argv",
        ["example.py", "--prompt", "Посчитай сумму", "--file", str(input_path)],
    )
    monkeypatch.chdir(tmp_path)

    runpy.run_path(str(tmp_path / "example.py"), run_name="__main__")

    output = capsys.readouterr().out
    assert "Файл рассчитан" in output
    assert "Создан файл: generated/result.csv" in output
    assert (tmp_path / "generated" / "result.csv").read_bytes() == output_payload
    assert captured["uploads"] == [(str(input_path), input_payload, "user_data")]
    assert captured["downloaded_file_id"] == "output-request-file-id"
    assert captured["upload_expiration"] == {
        "anchor": "created_at",
        "seconds": 172800,
    }
    assert captured["chunk_size"] == 64 * 1024
    assert captured["deleted_files"] == [
        "input-request-file-id",
        "output-request-file-id",
    ]
    assert captured["deleted_containers"] == ["container-request-id"]
    assert captured["deleted_responses"] == ["response-request-id"]

    request = captured["request"]
    assert request["tools"] == [
        {
            "type": "code_interpreter",
            "container": {
                "type": "auto",
                "memory_limit": "1g",
                "network_policy": {"type": "disabled"},
                "file_ids": ["input-request-file-id"],
            },
        }
    ]
    assert runtime_path.read_text(encoding="utf-8") == runtime_before == runtime_json
    assert "input-request-file-id" not in runtime_before
    assert "output-request-file-id" not in runtime_before
    assert "container-request-id" not in runtime_before

    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        combined = b"\n".join(archive.read(name) for name in archive.namelist())
    assert input_payload not in combined
    assert b"input-request-file-id" not in combined
    assert b"output-request-file-id" not in combined
    assert b"container-request-id" not in combined


def test_repository_code_interpreter_exports_match_the_runtime_compiler() -> None:
    specification_record = json.loads(
        (CODE_INTERPRETER_EXAMPLE_DIR / "agent-specification.json").read_text(
            encoding="utf-8"
        )
    )
    expected_runtime = json.loads(
        (CODE_INTERPRETER_EXAMPLE_DIR / "responses-agent-config.json").read_text(
            encoding="utf-8"
        )
    )

    specification = load_agent_specification(specification_record)
    compiled_runtime = json.loads(
        compile_agent_specification(specification, runtime=RUNTIME).to_json()
    )

    assert compiled_runtime == expected_runtime
    serialized_exports = json.dumps(
        {"specification": specification_record, "runtime": expected_runtime}
    )
    assert "file_ids" not in serialized_exports
    assert "container_id" not in serialized_exports
    assert "api_key" not in serialized_exports
    assert TEST_FOLDER_ID not in serialized_exports


def test_next_steps_download_button_serves_generated_zip(monkeypatch) -> None:
    specification_object = _one_prompt_specification()
    _, runtime_json, specification = _bundle_for(specification_object)
    fake_streamlit = MagicMock()
    monkeypatch.setattr(user_guidance, "st", fake_streamlit)

    user_guidance.render_agent_next_steps(
        specification,
        runtime_json,
        key_prefix="verified-agent",
    )

    fake_streamlit.download_button.assert_called_once()
    call = fake_streamlit.download_button.call_args
    assert call.args == ("Скачать пакет для разработчика (.zip)",)
    assert call.kwargs["file_name"] == "generated-agent.zip"
    assert call.kwargs["mime"] == "application/zip"
    assert call.kwargs["key"] == "verified-agent-developer-bundle-download"
    with zipfile.ZipFile(io.BytesIO(call.kwargs["data"])) as archive:
        assert set(archive.namelist()) == EXPECTED_FILES
        assert archive.testzip() is None
        assert archive.read("responses-agent-config.json").decode() == runtime_json
        assert json.loads(archive.read("agent-specification.json")) == specification

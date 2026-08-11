import io
import json
from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock
import zipfile

from ai_studio_agent_builder.config import AgentRuntimeConfig
from agent_runtime import compile_agent_specification
from agent_specification import (
    AgentSpecification,
    KnowledgeSource,
    build_one_prompt_specification,
    build_rag_specification,
)
from ui import user_guidance
from ui.developer_bundle import build_developer_bundle


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

        readme = archive.read("README.md").decode()
        assert "### Bash (Linux, macOS, Git Bash)" in readme
        assert "### Windows PowerShell" in readme
        assert "### Windows Command Prompt (CMD)" in readme
        assert ".venv/bin/python example.py" in readme
        assert r".\.venv\Scripts\python.exe example.py" in readme
        assert r".venv\Scripts\python.exe example.py" in readme

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

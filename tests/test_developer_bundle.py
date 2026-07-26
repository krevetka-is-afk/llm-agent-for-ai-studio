import io
import json
import zipfile

from ui.developer_bundle import build_developer_bundle


EXPECTED_FILES = {
    ".env.example",
    "README.md",
    "agent-specification.json",
    "example.py",
    "responses-agent-config.json",
}


def test_developer_bundle_contains_runnable_secret_free_handoff() -> None:
    specification = {
        "template": "one_prompt",
        "purpose": "Помощник поддержки",
        "status": "ready",
    }
    runtime_json = json.dumps(
        {
            "schema_version": "1.0",
            "model_name": "gpt-oss-120b",
            "instructions": "Отвечай кратко.",
            "tools": [{"type": "web_search", "search_context_size": "medium"}],
            "temperature": 0.5,
            "max_output_tokens": 1000,
        },
        ensure_ascii=False,
    )

    bundle = build_developer_bundle(specification, runtime_json)

    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert set(archive.namelist()) == EXPECTED_FILES
        assert archive.read("responses-agent-config.json").decode() == runtime_json
        assert json.loads(archive.read("agent-specification.json")) == specification

        example = archive.read("example.py").decode()
        compile(example, "example.py", "exec")
        assert "client.responses.create" in example

        env_example = archive.read(".env.example").decode()
        assert "replace_with_api_key" in env_example
        assert "replace_with_folder_id" in env_example

        combined_text = "\n".join(
            archive.read(filename).decode() for filename in archive.namelist()
        )
        assert "AQAAAA-" not in combined_text
        assert "folder-1" not in combined_text

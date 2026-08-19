import json
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "code_interpreter"
    / "yandex_response_contract.json"
)


def test_code_interpreter_fixture_is_anonymized_and_covers_artifact_contract() -> None:
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    fixture = json.loads(fixture_text)

    assert fixture["status"] == "completed"
    assert fixture["model"] == "gpt://<folder_id>/gpt-oss-120b"
    assert fixture["output_text_contains_marker"] is True
    assert "response-" not in fixture_text
    assert "file-" not in fixture_text
    assert "container-" not in fixture_text

    code_calls = [
        item for item in fixture["output"] if item["type"] == "code_interpreter_call"
    ]
    assert code_calls
    assert code_calls[0]["container_id"] == "<container_id>"
    assert code_calls[0]["code_present"] is True

    annotations = [
        annotation
        for item in fixture["output"]
        for content in item.get("content", [])
        for annotation in content.get("annotations", [])
    ]
    assert annotations == [
        {
            "type": "container_file_citation",
            "fields": [
                "container_id",
                "end_index",
                "file_id",
                "filename",
                "start_index",
            ],
            "container_id": "<container_id>",
            "file_id": "<file_id>",
            "filename": "result.csv",
        }
    ]

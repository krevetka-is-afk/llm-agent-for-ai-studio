from pathlib import Path
from types import SimpleNamespace

from cryptography.fernet import Fernet
import pytest
from streamlit.testing.v1 import AppTest

from ai_interaction_service import (
    MAX_ATTACHMENTS_PER_REQUEST,
    MAX_TOTAL_UPLOAD_BYTES,
    UploadValidationError,
)
from ai_studio_agent_builder.application.file_policy import MAX_UPLOAD_BYTES
from ui.agent_test_panel import (
    RESPONSE_ID_HELP,
    TEST_INPUT_HELP,
    TOTAL_TOKENS_HELP,
)
from ui.app import _attachment_record, _validate_uploaded_files
from ai_interaction_service import Attachment


def test_web_ui_starts_in_disconnected_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(
        "YC_API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii")
    )
    monkeypatch.setenv("YC_API_KEY_DB_PATH", str(tmp_path / "api-keys.db"))

    app = AppTest.from_file("src/ui/app.py", default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "AI Studio Chat"
    assert app.chat_input[0].disabled
    assert app.text_input[0].label == "ID каталога"
    assert app.text_input[1].label == "API-ключ"
    assert any(element.value == "После создания" for element in app.subheader)
    assert any("Куда идти с результатом?" in element.label for element in app.expander)


def test_result_view_renders_multiple_agent_downloads_without_id_collision() -> None:
    app = AppTest.from_string(
        """
from ui.result_view import render_result_parts

specification = {
    "kind": "agent_specification",
    "specification": {
        "template": "one_prompt",
        "status": "complete",
    },
}
render_result_parts([specification], key_prefix="first-assistant")
render_result_parts([specification], key_prefix="second-assistant")
"""
    ).run()

    assert not app.exception


def test_result_view_renders_independent_agent_test_panels_and_persists_preview() -> (
    None
):
    app = AppTest.from_string(
        """
from ai_interaction_service import AgentTestResult
from ui.agent_test_panel import AgentSpecificationActions
from ui.result_view import render_result_parts

def runtime_json(specification):
    return '{"schema_version":"1.0","model_name":"test-model"}'

def test_agent(specification, user_input, request_id):
    return AgentTestResult(
        response_id="resp-test",
        output_text=f"Ответ: {user_input}",
        citations=(),
        total_tokens=7,
    )

actions = AgentSpecificationActions(
    runtime_config_json=runtime_json,
    test_agent=test_agent,
)
specification = {
    "kind": "agent_specification",
    "specification": {
        "template": "one_prompt",
        "status": "ready",
    },
}
render_result_parts(
    [specification],
    key_prefix="first-assistant",
    agent_actions=actions,
)
render_result_parts(
    [specification],
    key_prefix="second-assistant",
    agent_actions=actions,
)
"""
    ).run()

    assert not app.exception
    assert len(app.text_area) == 2
    assert len(app.button) == 2
    assert app.text_area[0].help == TEST_INPUT_HELP

    app.text_area[0].set_value("Проверочный запрос")
    app.button[0].click()
    app.run()

    assert not app.exception
    assert any("Ответ: Проверочный запрос" in element.value for element in app.markdown)
    assert any(
        element.label == "Всего токенов"
        and element.value == "7"
        and element.help == TOTAL_TOKENS_HELP
        for element in app.metric
    )
    assert any(
        "Агент проверен. Что делать дальше?" in element.value
        for element in app.markdown
    )
    assert any(
        element.label == "Идентификатор тестового ответа" for element in app.expander
    )
    assert any(
        element.value == "**Response ID**" and element.help == RESPONSE_ID_HELP
        for element in app.markdown
    )


def test_result_view_hides_test_action_when_disconnected() -> None:
    app = AppTest.from_string(
        """
from ui.agent_test_panel import AgentSpecificationActions
from ui.result_view import render_result_parts

actions = AgentSpecificationActions(
    runtime_config_json=lambda specification: '{"schema_version":"1.0"}',
)
render_result_parts(
    [{
        "kind": "agent_specification",
        "specification": {"template": "one_prompt", "status": "ready"},
    }],
    key_prefix="disconnected",
    agent_actions=actions,
)
"""
    ).run()

    assert not app.exception
    assert len(app.text_area) == 0
    assert len(app.button) == 0
    assert any("Подключитесь к AI Studio" in element.value for element in app.info)


def test_result_view_keeps_json_card_but_hides_runtime_for_malformed_spec() -> None:
    app = AppTest.from_string(
        """
from ui.agent_test_panel import AgentSpecificationActions
from ui.result_view import render_result_parts

def reject_runtime(specification):
    raise ValueError("raw malformed details")

render_result_parts(
    [{
        "kind": "agent_specification",
        "specification": {"template": "rag", "status": "ready"},
    }],
    key_prefix="malformed",
    agent_actions=AgentSpecificationActions(
        runtime_config_json=reject_runtime,
        test_agent=lambda specification, user_input, request_id: None,
    ),
)
"""
    ).run()

    assert not app.exception
    assert len(app.text_area) == 0
    assert any(
        "несовместима с текущим runtime" in element.value for element in app.warning
    )
    assert all("raw malformed details" not in element.value for element in app.warning)


def _upload(name: str, size: int) -> SimpleNamespace:
    return SimpleNamespace(name=name, size=size)


def test_web_ui_rejects_too_many_files_before_reading_content() -> None:
    files = [
        _upload(f"file-{index}.txt", 1)
        for index in range(MAX_ATTACHMENTS_PER_REQUEST + 1)
    ]

    with pytest.raises(UploadValidationError, match="не более"):
        _validate_uploaded_files(files)


def test_web_ui_rejects_oversized_file_before_reading_content() -> None:
    with pytest.raises(UploadValidationError, match="превышает лимит"):
        _validate_uploaded_files([_upload("large.pdf", MAX_UPLOAD_BYTES + 1)])


def test_web_ui_rejects_oversized_total_before_reading_content() -> None:
    size = MAX_TOTAL_UPLOAD_BYTES // MAX_ATTACHMENTS_PER_REQUEST + 1
    files = [
        _upload(f"file-{index}.txt", size)
        for index in range(MAX_ATTACHMENTS_PER_REQUEST)
    ]

    with pytest.raises(UploadValidationError, match="Общий размер"):
        _validate_uploaded_files(files)


def test_attachment_record_keeps_internal_and_original_filenames_separate() -> None:
    attachment = Attachment(filename="generated-report.txt", display_name="report.txt")
    uploaded_file = SimpleNamespace(
        name="report.txt",
        type="text/plain",
        size=4,
    )

    assert _attachment_record(attachment, uploaded_file) == {
        "filename": "generated-report.txt",
        "original_filename": "report.txt",
        "mime_type": "text/plain",
        "size": 4,
    }

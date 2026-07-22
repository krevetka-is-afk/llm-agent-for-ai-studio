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
from custom_agents.tools.upload_files import MAX_UPLOAD_BYTES
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

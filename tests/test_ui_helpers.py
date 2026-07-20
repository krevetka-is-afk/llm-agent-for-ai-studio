from types import SimpleNamespace

from ai_interaction_service import Attachment, UploadValidationError
from ui.attachments import preview_kind_for_mime
from ui.chat_flow import build_user_content, interaction_error_message
from ui.uploads import attachment_record


def test_attachment_record_preserves_saved_and_original_filename() -> None:
    attachment = Attachment(filename="stored.pdf", display_name="report.pdf")
    upload = SimpleNamespace(
        name="report.pdf",
        type="application/pdf",
        size=512,
    )

    assert attachment_record(attachment, upload) == {
        "filename": "stored.pdf",
        "original_filename": "report.pdf",
        "mime_type": "application/pdf",
        "size": 512,
    }


def test_pdf_preview_is_download_only() -> None:
    assert preview_kind_for_mime("application/pdf") == "download_only"


def test_chat_flow_builds_fallback_content_for_multiple_files() -> None:
    uploads = [SimpleNamespace(name="one.txt"), SimpleNamespace(name="two.txt")]

    assert build_user_content("", uploads) == "Прикреплены файлы: one.txt, two.txt"


def test_chat_flow_maps_known_and_unknown_errors() -> None:
    assert interaction_error_message(UploadValidationError("too large")) == "too large"
    assert interaction_error_message(RuntimeError("secret details")) == (
        "Не удалось выполнить запрос к AI Studio. Повторите попытку."
    )

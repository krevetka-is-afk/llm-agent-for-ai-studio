import json
from types import SimpleNamespace
from typing import Any, cast

from agent_runner import AgentProviderError, VectorStoreUnavailableError
from ai_interaction_service import (
    AIInteractionService,
    AgentTestInputError,
    AgentTestRequest,
    AgentTestResult,
    Attachment,
    UploadValidationError,
)
from ui.api_key_store import ApiKeyConnection
from ui.agent_test_panel import (
    agent_test_error_message,
    citation_markdown,
    preview_state_key,
    specification_fingerprint,
)
from ui.attachments import preview_kind_for_mime
from ui.chat_flow import build_user_content, interaction_error_message
from ui.chat_flow import build_agent_specification_actions
from ui.result_view import agent_specification_json
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


def test_agent_specification_json_preserves_unicode_and_nested_fields() -> None:
    payload = agent_specification_json(
        {
            "template": "one_prompt",
            "purpose": "Помощник службы поддержки",
            "tools": [],
        }
    )

    assert "Помощник службы поддержки" in payload
    assert json.loads(payload)["template"] == "one_prompt"


def test_agent_specification_fingerprint_is_canonical_and_content_sensitive() -> None:
    first = {"template": "one_prompt", "parameters": {"a": 1, "b": 2}}
    reordered = {"parameters": {"b": 2, "a": 1}, "template": "one_prompt"}
    changed = {"template": "one_prompt", "parameters": {"a": 1, "b": 3}}

    assert specification_fingerprint(first) == specification_fingerprint(reordered)
    assert specification_fingerprint(first) != specification_fingerprint(changed)
    assert preview_state_key("message-1") != preview_state_key("message-2")


def test_agent_test_errors_are_bounded_and_actionable() -> None:
    unavailable = VectorStoreUnavailableError("vs-secret", "expired")

    assert agent_test_error_message(unavailable) == (
        "Индекс недоступен или истёк. Пересоздайте RAG-конфигурацию."
    )
    assert "vs-secret" not in agent_test_error_message(unavailable)
    assert agent_test_error_message(AgentProviderError()) == (
        "AI Studio отклонил запуск агента. Проверьте подключение и права."
    )
    assert agent_test_error_message(AgentTestInputError("Введите запрос")) == (
        "Введите запрос"
    )
    assert "secret" not in agent_test_error_message(
        RuntimeError("api_key=secret-provider-body")
    )


def test_citation_markdown_uses_compact_domain_but_keeps_full_url() -> None:
    url = (
        "https://ru.wikipedia.org/wiki/"
        "%D0%A4%D0%B8%D0%BD%D0%B0%D0%BB_%D1%87%D0%B5%D0%BC%D0%BF%D0%B8%D0%BE"
        "%D0%BD%D0%B0%D1%82%D0%B0_%D0%BC%D0%B8%D1%80%D0%B0"
    )

    markdown = citation_markdown(
        1,
        "Финал чемпионата мира по футболу 2026 — Википедия",
        url,
    )

    assert "ru.wikipedia.org ↗" in markdown
    assert url in markdown
    assert markdown.count(url) == 1
    assert markdown.startswith(
        "1. Финал чемпионата мира по футболу 2026 — Википедия — "
    )


def test_citation_markdown_shortens_long_non_url_reference() -> None:
    reference = "file-" + ("a" * 100)

    markdown = citation_markdown(2, "Внутренний документ", reference)

    assert reference not in markdown
    assert "…" in markdown
    assert len(markdown) < len(reference)


def test_chat_flow_builds_callbacks_without_exposing_connection_to_result_view() -> (
    None
):
    class FakeService:
        def __init__(self) -> None:
            self.test_request: AgentTestRequest | None = None

        def prepare_agent_runtime(self, specification):
            return SimpleNamespace(to_json=lambda: '{"model_name":"test-model"}')

        async def test_agent_specification(self, request):
            self.test_request = request
            return AgentTestResult(
                response_id="resp-1",
                output_text="Answer",
                citations=(),
            )

    service = FakeService()
    disconnected = build_agent_specification_actions(
        cast(AIInteractionService, cast(Any, service)),
        None,
        "web-user",
    )
    assert disconnected.test_agent is None
    assert json.loads(disconnected.runtime_config_json({})) == {
        "model_name": "test-model"
    }

    connected = build_agent_specification_actions(
        cast(AIInteractionService, cast(Any, service)),
        ApiKeyConnection(api_key="AQAAAA-secret", folder_id="folder-1"),
        "web-user",
    )
    assert connected.test_agent is not None

    result = connected.test_agent({}, "Question", "request-1")

    assert result.output_text == "Answer"
    assert service.test_request is not None
    assert service.test_request.user_id == "web-user"
    assert service.test_request.request_id == "request-1"
    assert service.test_request.credentials.folder_id == "folder-1"

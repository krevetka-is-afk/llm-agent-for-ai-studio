import json
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ai_studio_agent_builder.application.errors import (
    AIStudioRequestError,
    VectorIndexUnavailableError,
)
from ai_studio_agent_builder.application.file_policy import MAX_UPLOAD_BYTES
from ai_studio_agent_builder.application.interaction import (
    AIInteraction,
    AgentTestInputError,
    AgentTestRequest,
    AgentTestResult,
    Attachment,
    UploadValidationError,
)
from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentProviderError,
    VectorStoreUnavailableError,
)
from ai_studio_agent_builder.application.ports.api_key_store import (
    ApiKeyConnection,
)
from ai_studio_agent_builder.presentation.streamlit.agent_test_panel import (
    agent_test_error_message,
    citation_markdown,
    has_code_interpreter_tool,
    preview_request_fingerprint,
    preview_state_key,
    specification_fingerprint,
)
from ai_studio_agent_builder.presentation.streamlit.attachments import (
    generated_preview_kind_for_mime,
    preview_kind_for_mime,
)
from ai_studio_agent_builder.presentation.streamlit.chat_flow import (
    build_agent_specification_actions,
    build_user_content,
    conversation_attachments,
    interaction_error_message,
)
from ai_studio_agent_builder.presentation.streamlit.markdown_renderer import (
    normalize_latex_delimiters,
)
from ai_studio_agent_builder.presentation.streamlit.result_view import (
    agent_specification_json,
)
from ai_studio_agent_builder.presentation.streamlit.uploads import attachment_record


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


def test_generated_artifact_preview_uses_strict_mime_allowlist() -> None:
    assert generated_preview_kind_for_mime("image/png") == "image"
    assert generated_preview_kind_for_mime("text/csv") == "text"
    for mime_type in (
        "image/svg+xml",
        "text/html",
        "application/xml",
        "application/octet-stream",
    ):
        assert generated_preview_kind_for_mime(mime_type) == "download_only"


def test_chat_flow_builds_fallback_content_for_multiple_files() -> None:
    uploads = [SimpleNamespace(name="one.txt"), SimpleNamespace(name="two.txt")]

    assert build_user_content("", uploads) == "Прикреплены файлы: one.txt, two.txt"


def test_chat_flow_recovers_attachment_after_interjected_turns() -> None:
    messages = [
        {
            "role": "user",
            "content": "Создай бота по этому файлу",
            "attachments": [
                {
                    "filename": "stored-bakery.csv",
                    "original_filename": "bakery.csv",
                    "mime_type": "text/csv",
                    "size": 12,
                    "file_id": "untrusted-provider-id",
                }
            ],
        },
        {"role": "assistant", "content": "Уточните аудиторию"},
        {
            "role": "user",
            "content": "Посторонний вброс",
            "attachments": [
                {
                    "filename": "../outside.csv",
                    "original_filename": "outside.csv",
                }
            ],
        },
        {"role": "assistant", "content": "Запрос вне рабочей области"},
        {"role": "user", "content": "Продолжим: аудитория — покупатели"},
    ]

    assert conversation_attachments(messages) == (
        Attachment(
            filename="stored-bakery.csv",
            display_name="bakery.csv",
        ),
    )


def test_markdown_renderer_normalizes_model_latex_delimiters() -> None:
    response = r"""Для оценки использовали метрику
[ \text{score} = \frac{\text{вес (г)} \times \text{ккал}}{\text{цена (₽)}} ]

Inline: \(x^2 + y^2\). Standard block:
\[
\sum_{i=1}^{n} i
\]
"""

    assert (
        normalize_latex_delimiters(response)
        == r"""Для оценки использовали метрику
$$
\text{score} = \frac{\text{вес (г)} \times \text{ккал}}{\text{цена (₽)}}
$$

Inline: $x^2 + y^2$. Standard block:
$$
\sum_{i=1}^{n} i
$$
"""
    )


def test_markdown_renderer_preserves_non_math_and_existing_dollar_math() -> None:
    response = r"""Обычные [квадратные скобки] и [ссылка](https://example.com).

Цена $100, формула $x + y$, блок:
$$
x = y
$$

```text
[ \frac{raw}{latex} ]
\[raw\]
```
"""

    assert normalize_latex_delimiters(response) == response


def test_chat_flow_maps_known_and_unknown_errors() -> None:
    assert interaction_error_message(AIStudioRequestError()) == (
        "AI Studio отклонил запрос. Проверьте ключ, каталог и права."
    )
    assert interaction_error_message(UploadValidationError("too large")) == "too large"
    assert interaction_error_message(VectorIndexUnavailableError()) == (
        "AI Studio не завершил создание индекса. Повторите попытку позднее."
    )
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


class _PreviewUpload:
    def __init__(self, name: str, data: bytes, mime_type: str = "text/plain") -> None:
        self.name = name
        self.data = data
        self.type = mime_type
        self.size = len(data)
        self.read_count = 0

    def getvalue(self) -> bytes:
        self.read_count += 1
        return self.data


def test_preview_fingerprint_includes_validated_file_name_type_and_content() -> None:
    specification = {"template": "one_prompt", "tools": []}
    first = _PreviewUpload("input.csv", b"value\n1\n", "text/csv")
    same = _PreviewUpload("input.csv", b"value\n1\n", "text/csv")
    changed = _PreviewUpload("input.csv", b"value\n2\n", "text/csv")

    first_fingerprint = preview_request_fingerprint(specification, (first,))

    assert first_fingerprint == preview_request_fingerprint(specification, (same,))
    assert first_fingerprint != preview_request_fingerprint(
        specification,
        (changed,),
    )


def test_preview_fingerprint_includes_inherited_conversation_files() -> None:
    specification = {
        "template": "one_prompt",
        "tools": [{"tool_id": "code_interpreter", "parameters": {}}],
    }
    bakery = Attachment("stored-bakery.csv", display_name="bakery.csv")
    prices = Attachment("stored-prices.csv", display_name="prices.csv")

    bakery_fingerprint = preview_request_fingerprint(
        specification,
        (),
        (bakery,),
    )

    assert bakery_fingerprint == preview_request_fingerprint(
        specification,
        (),
        (bakery,),
    )
    assert bakery_fingerprint != preview_request_fingerprint(
        specification,
        (),
        (prices,),
    )


def test_preview_fingerprint_validates_metadata_before_reading_content() -> None:
    oversized = _PreviewUpload("large.bin", b"")
    oversized.size = MAX_UPLOAD_BYTES + 1

    with pytest.raises(UploadValidationError):
        preview_request_fingerprint({}, (oversized,))

    assert oversized.read_count == 0


def test_code_interpreter_uploader_detection_uses_public_tool_descriptor() -> None:
    assert has_code_interpreter_tool(
        {"tools": [{"tool_id": "code_interpreter", "parameters": {}}]}
    )
    assert not has_code_interpreter_tool({"tools": [{"tool_id": "knowledge_search"}]})
    assert not has_code_interpreter_tool({"tools": "code_interpreter"})


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
            self.generated_file_reads: list[tuple[str, str]] = []
            self.saved_preview_files: list[tuple[str, str, bytes, str | None]] = []

        def prepare_agent_runtime(self, specification):
            return SimpleNamespace(to_json=lambda: '{"model_name":"test-model"}')

        async def test_agent_specification(self, request):
            self.test_request = request
            return AgentTestResult(
                response_id="resp-1",
                output_text="Answer",
                citations=(),
            )

        def read_generated_file(self, user_id: str, local_name: str) -> bytes:
            self.generated_file_reads.append((user_id, local_name))
            return b"generated"

        def save_attachment(
            self,
            user_id: str,
            original_filename: str,
            content: bytes,
            caption: str | None = None,
        ) -> Attachment:
            self.saved_preview_files.append(
                (user_id, original_filename, content, caption)
            )
            return Attachment(
                filename="internal-input.csv",
                display_name=original_filename,
            )

    service = FakeService()
    disconnected = build_agent_specification_actions(
        cast(AIInteraction, cast(Any, service)),
        None,
        "web-user",
    )
    assert disconnected.test_agent is None
    assert json.loads(disconnected.runtime_config_json({})) == {
        "model_name": "test-model"
    }

    connected = build_agent_specification_actions(
        cast(AIInteraction, cast(Any, service)),
        ApiKeyConnection(api_key="AQAAAA-secret", folder_id="folder-1"),
        "web-user",
    )
    assert connected.test_agent is not None

    upload = _PreviewUpload("input.csv", b"value\n1\n", "text/csv")
    result = connected.test_agent({}, "Question", "request-1", (upload,))

    assert result.output_text == "Answer"
    assert service.test_request is not None
    assert service.test_request.user_id == "web-user"
    assert service.test_request.request_id == "request-1"
    assert service.test_request.credentials.folder_id == "folder-1"
    assert service.test_request.attachments == (
        Attachment(filename="internal-input.csv", display_name="input.csv"),
    )
    assert service.saved_preview_files == [
        ("web-user", "input.csv", b"value\n1\n", "Question")
    ]
    assert connected.generated_file_reader is not None
    assert connected.generated_file_reader("stored.csv") == b"generated"
    assert service.generated_file_reads == [("web-user", "stored.csv")]


def test_chat_flow_scopes_conversation_files_to_code_interpreter_preview() -> None:
    class FakeService:
        def __init__(self) -> None:
            self.test_request: AgentTestRequest | None = None
            self.saved_preview_files: list[str] = []

        def prepare_agent_runtime(self, specification):
            return SimpleNamespace(to_json=lambda: "{}")

        async def test_agent_specification(self, request):
            self.test_request = request
            return AgentTestResult(
                response_id="resp-1",
                output_text="Answer",
                citations=(),
            )

        def save_attachment(
            self,
            user_id: str,
            original_filename: str,
            content: bytes,
            caption: str | None = None,
        ) -> Attachment:
            self.saved_preview_files.append(original_filename)
            return Attachment(filename="unexpected-new-upload.csv")

        def read_generated_file(self, user_id: str, local_name: str) -> bytes:
            return b""

    service = FakeService()
    inherited = Attachment(
        filename="stored-bakery.csv",
        display_name="bakery.csv",
    )
    actions = build_agent_specification_actions(
        cast(AIInteraction, cast(Any, service)),
        ApiKeyConnection(api_key="AQAAAA-secret", folder_id="folder-1"),
        "web-user",
        conversation_files=(inherited,),
    )

    assert actions.test_agent is not None
    actions.test_agent(
        {
            "template": "one_prompt",
            "tools": [{"tool_id": "code_interpreter", "parameters": {}}],
        },
        "Построй график",
        "request-1",
        (),
    )

    assert service.test_request is not None
    assert service.test_request.attachments == (inherited,)
    assert service.saved_preview_files == []

    actions.test_agent(
        {"template": "one_prompt", "tools": []},
        "Ответь без файлов",
        "request-2",
        (),
    )

    assert service.test_request.attachments == ()

    overflow_actions = build_agent_specification_actions(
        cast(AIInteraction, cast(Any, service)),
        ApiKeyConnection(api_key="AQAAAA-secret", folder_id="folder-1"),
        "web-user",
        conversation_files=tuple(
            Attachment(f"stored-{index}.csv") for index in range(5)
        ),
    )
    assert overflow_actions.test_agent is not None

    with pytest.raises(AgentTestInputError, match="не более 5 файлов"):
        overflow_actions.test_agent(
            {
                "template": "one_prompt",
                "tools": [{"tool_id": "code_interpreter", "parameters": {}}],
            },
            "Построй график",
            "request-3",
            (_PreviewUpload("extra.csv", b"value\n1\n", "text/csv"),),
        )

    assert service.saved_preview_files == []

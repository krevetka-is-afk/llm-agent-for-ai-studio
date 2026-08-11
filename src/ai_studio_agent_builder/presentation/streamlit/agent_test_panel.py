import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import uuid4

import streamlit as st

from ai_studio_agent_builder.application.interaction import (
    AgentTestInputError,
    AgentTestResult,
)
from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentProviderError,
    AgentProviderTimeoutError,
    AgentRunPreview,
    VectorStoreUnavailableError,
)
from ai_studio_agent_builder.domain.runtime import AgentRuntimeCompilationError
from ai_studio_agent_builder.domain.specification import (
    InvalidSpecificationRecordError,
)

from .user_guidance import render_agent_next_steps


PREVIEW_STATE_PREFIX = "agent-test-preview:"
TEST_INPUT_HELP = (
    "Отдельный вопрос для проверки уже собранного агента. Он не изменяет "
    "инструкцию или основной диалог Agent Builder."
)
SOURCES_HELP = (
    "Ссылки или файлы, которые Web Search или File Search использовал при "
    "подготовке ответа."
)
INPUT_TOKENS_HELP = (
    "Объём инструкции, пользовательского вопроса и дополнительного контекста, "
    "отправленных модели."
)
OUTPUT_TOKENS_HELP = "Объём ответа, сгенерированного моделью."
TOTAL_TOKENS_HELP = (
    "Суммарное потребление токенов за этот тестовый запрос. Оно помогает "
    "оценивать лимиты и расходы."
)
RESPONSE_ID_HELP = (
    "Уникальный ID одного тестового обращения к Responses API. Он нужен для "
    "поиска запроса в логах и диагностики. Это не ID постоянного агента."
)
RUNTIME_CONFIG_HELP = (
    "Точная конфигурация, использованная для теста: модель, инструкция, "
    "инструменты и параметры генерации. API-ключ, folder ID и тестовый вопрос "
    "в файл не входят."
)
MAX_REFERENCE_LABEL_LENGTH = 48

RuntimeConfigCallback = Callable[[Mapping[str, Any]], str]
AgentTestCallback = Callable[
    [Mapping[str, Any], str, str],
    AgentTestResult,
]


@dataclass(frozen=True)
class AgentSpecificationActions:
    runtime_config_json: RuntimeConfigCallback
    test_agent: AgentTestCallback | None = None


@dataclass(frozen=True)
class AgentPreviewState:
    specification_fingerprint: str
    result: AgentTestResult


def citation_markdown(number: int, title: str, reference: str | None) -> str:
    safe_title = _escape_markdown_text(_compact_unbroken_text(title, 96))
    if not reference:
        return f"{number}. {safe_title}"

    normalized_reference = reference.strip()
    parsed = urlsplit(normalized_reference)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        hostname = parsed.hostname.removeprefix("www.")
        label = _compact_text(hostname, MAX_REFERENCE_LABEL_LENGTH) + " ↗"
        href = quote(
            normalized_reference,
            safe=":/?#[]@!$&'()*+,;=%",
        )
        link = f"[{_escape_markdown_text(label)}](<{href}>)"
        if normalized_reference == title:
            return f"{number}. {link}"
        return f"{number}. {safe_title} — {link}"

    if normalized_reference == title:
        return (
            f"{number}. "
            f"{_escape_markdown_text(_compact_text(title, MAX_REFERENCE_LABEL_LENGTH))}"
        )
    compact_reference = _escape_markdown_text(
        _compact_text(normalized_reference, MAX_REFERENCE_LABEL_LENGTH)
    )
    return f"{number}. {safe_title} — {compact_reference}"


def _compact_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip() + "…"


def _compact_unbroken_text(value: str, max_length: int) -> str:
    if any(character.isspace() for character in value):
        return value
    return _compact_text(value, max_length)


def _escape_markdown_text(value: str) -> str:
    escaped_characters = frozenset("\\`*_[]()<>")
    return "".join(
        f"\\{character}" if character in escaped_characters else character
        for character in value
    )


def render_agent_test_panel(
    specification: Mapping[str, Any],
    *,
    key_prefix: str,
    actions: AgentSpecificationActions,
) -> None:
    try:
        runtime_json = actions.runtime_config_json(specification)
    except (
        InvalidSpecificationRecordError,
        AgentRuntimeCompilationError,
        ValueError,
    ):
        st.warning(
            "Эта сохранённая спецификация несовместима с текущим runtime. "
            "JSON по-прежнему можно скачать."
        )
        return
    except Exception:
        st.warning("Не удалось подготовить runtime-конфигурацию.")
        return

    fingerprint = specification_fingerprint(specification)
    state_key = preview_state_key(key_prefix)
    cached_preview = st.session_state.get(state_key)
    if (
        isinstance(cached_preview, AgentPreviewState)
        and cached_preview.specification_fingerprint != fingerprint
    ):
        del st.session_state[state_key]
        cached_preview = None

    if specification.get("template") == "rag":
        ttl_days = _rag_ttl_days(specification)
        st.warning(
            "RAG использует временный векторный индекс"
            + (f" со сроком хранения {ttl_days} день." if ttl_days is not None else ".")
        )

    if actions.test_agent is None:
        st.info("Подключитесь к AI Studio, чтобы протестировать агента.")
    else:
        with st.form(f"{key_prefix}-agent-test-form", clear_on_submit=False):
            user_input = st.text_area(
                "Тестовый запрос к агенту",
                key=f"{key_prefix}-agent-test-input",
                max_chars=10_000,
                help=TEST_INPUT_HELP,
            )
            submitted = st.form_submit_button(
                "Протестировать агента",
                type="primary",
                help=(
                    "Выполняет один stateless-запрос к Responses API с текущими "
                    "настройками агента."
                ),
            )
        if submitted:
            if not user_input.strip():
                st.error("Введите тестовый запрос.")
            else:
                try:
                    with st.spinner("Агент выполняет запрос..."):
                        result = actions.test_agent(
                            specification,
                            user_input,
                            uuid4().hex,
                        )
                except Exception as exc:
                    st.error(agent_test_error_message(exc))
                else:
                    cached_preview = AgentPreviewState(
                        specification_fingerprint=fingerprint,
                        result=result,
                    )
                    st.session_state[state_key] = cached_preview

    if isinstance(cached_preview, AgentPreviewState):
        render_agent_preview(cached_preview.result)
        render_agent_next_steps(
            specification,
            runtime_json,
            key_prefix=key_prefix,
        )

    with st.expander("Технический экспорт", expanded=False):
        st.markdown(
            "**Конфигурация Responses API**",
            help=RUNTIME_CONFIG_HELP,
        )
        st.caption(
            "Поле `input` задаётся отдельно при каждом запуске. "
            "Секреты и ID каталога не экспортируются."
        )
        st.download_button(
            "Скачать Responses API config (.json)",
            data=runtime_json,
            file_name="responses-agent-config.json",
            mime="application/json",
            key=f"{key_prefix}-runtime-config-download",
            help=RUNTIME_CONFIG_HELP,
        )


def render_agent_preview(result: AgentTestResult | AgentRunPreview) -> None:
    st.markdown("#### Результат тестирования")
    if result.output_text:
        st.markdown(result.output_text)
    else:
        st.info("Агент завершил запрос без текстового ответа.")

    if result.citations:
        st.markdown("**Источники ответа**", help=SOURCES_HELP)
        for number, citation in enumerate(result.citations, start=1):
            title = (
                citation.title or citation.filename or citation.file_id or "Источник"
            )
            reference = citation.url or citation.filename or citation.file_id
            st.markdown(
                citation_markdown(
                    number,
                    title,
                    reference,
                )
            )

    token_metrics = [
        ("Входные токены", result.input_tokens, INPUT_TOKENS_HELP),
        ("Токены ответа", result.output_tokens, OUTPUT_TOKENS_HELP),
        ("Всего токенов", result.total_tokens, TOTAL_TOKENS_HELP),
    ]
    visible_token_metrics = [
        metric for metric in token_metrics if metric[1] is not None
    ]
    if visible_token_metrics:
        st.markdown(
            "**Использование токенов**",
            help=(
                "Токены — условные части текста, по которым считаются лимиты "
                "модели и потребление API."
            ),
        )
        columns = st.columns(len(visible_token_metrics))
        for column, (label, value, help_text) in zip(
            columns,
            visible_token_metrics,
            strict=True,
        ):
            with column:
                st.metric(
                    label,
                    value,
                    help=help_text,
                    border=True,
                )

    with st.expander("Идентификатор тестового ответа", expanded=False):
        st.markdown("**Response ID**", help=RESPONSE_ID_HELP)
        st.code(result.response_id or "не предоставлен", language=None)
        st.caption(
            "Идентификатор нужен для логов и диагностики. "
            "Это не `agent_id` и не постоянный диалог."
        )


def agent_test_error_message(exc: Exception) -> str:
    if isinstance(exc, VectorStoreUnavailableError):
        return "Индекс недоступен или истёк. Пересоздайте RAG-конфигурацию."
    if isinstance(exc, AgentProviderTimeoutError):
        return "AI Studio не успел выполнить запрос. Повторите попытку позднее."
    if isinstance(exc, AgentProviderError):
        return "AI Studio отклонил запуск агента. Проверьте подключение и права."
    if isinstance(exc, AgentTestInputError):
        return str(exc)
    if isinstance(
        exc,
        (InvalidSpecificationRecordError, AgentRuntimeCompilationError),
    ):
        return "Спецификация несовместима с текущим runtime."
    return "Не удалось протестировать агента. Повторите попытку."


def specification_fingerprint(specification: Mapping[str, Any]) -> str:
    canonical_json = json.dumps(
        dict(specification),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def preview_state_key(key_prefix: str) -> str:
    return f"{PREVIEW_STATE_PREFIX}{key_prefix}"


def clear_agent_test_previews() -> None:
    for key in tuple(st.session_state):
        if isinstance(key, str) and key.startswith(PREVIEW_STATE_PREFIX):
            del st.session_state[key]


def _rag_ttl_days(specification: Mapping[str, Any]) -> int | None:
    parameters = specification.get("parameters")
    if not isinstance(parameters, Mapping):
        return None
    ttl_days = parameters.get("ttl_days")
    if isinstance(ttl_days, int) and not isinstance(ttl_days, bool):
        return ttl_days
    return None

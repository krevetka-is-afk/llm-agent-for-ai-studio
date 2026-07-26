import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import streamlit as st

from agent_runner import (
    AgentProviderError,
    AgentProviderTimeoutError,
    AgentRunPreview,
    VectorStoreUnavailableError,
)
from agent_runtime import AgentRuntimeCompilationError
from agent_specification import InvalidSpecificationRecordError
from ai_interaction_service import AgentTestInputError, AgentTestResult


PREVIEW_STATE_PREFIX = "agent-test-preview:"

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
            )
            submitted = st.form_submit_button(
                "Протестировать агента",
                type="primary",
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

    with st.expander("Расширенные настройки", expanded=False):
        st.caption("Поле input задаётся приложением отдельно при каждом запуске.")
        st.download_button(
            "Скачать Responses API config",
            data=runtime_json,
            file_name="responses-agent-config.json",
            mime="application/json",
            key=f"{key_prefix}-runtime-config-download",
        )


def render_agent_preview(result: AgentTestResult | AgentRunPreview) -> None:
    st.markdown("#### Результат тестирования")
    if result.output_text:
        st.markdown(result.output_text)
    else:
        st.info("Агент завершил запрос без текстового ответа.")

    if result.citations:
        st.markdown("**Источники**")
        for number, citation in enumerate(result.citations, start=1):
            title = (
                citation.title or citation.filename or citation.file_id or "Источник"
            )
            reference = citation.url or citation.filename or citation.file_id
            st.write(
                f"{number}. {title}"
                + (f" — {reference}" if reference and reference != title else "")
            )

    token_parts = [
        f"вход: {result.input_tokens}" if result.input_tokens is not None else None,
        f"выход: {result.output_tokens}" if result.output_tokens is not None else None,
        f"всего: {result.total_tokens}" if result.total_tokens is not None else None,
    ]
    visible_token_parts = [part for part in token_parts if part is not None]
    if visible_token_parts:
        st.caption("Токены — " + ", ".join(visible_token_parts))

    with st.expander("Технические детали", expanded=False):
        st.code(result.response_id or "не предоставлен", language=None)


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

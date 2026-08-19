import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

import streamlit as st

from .agent_test_panel import (
    AgentSpecificationActions,
    render_agent_test_panel,
)
from .markdown_renderer import render_markdown


def render_result_parts(
    parts: Sequence[Any],
    *,
    key_prefix: str,
    agent_actions: AgentSpecificationActions | None = None,
) -> None:
    for part_index, raw_part in enumerate(parts):
        if not isinstance(raw_part, Mapping):
            continue
        part = cast(Mapping[str, Any], raw_part)
        kind = part.get("kind")
        if kind == "vector_index":
            render_vector_index_result(part)
        elif kind == "agent_specification":
            render_agent_specification_result(
                part,
                download_key=f"{key_prefix}-agent-specification-{part_index}",
                panel_key=f"{key_prefix}-agent-test-{part_index}",
                actions=agent_actions,
            )
        elif kind == "markdown":
            text = part.get("text")
            if isinstance(text, str) and text:
                render_markdown(text)


def render_agent_specification_result(
    part: Mapping[str, Any],
    *,
    download_key: str,
    panel_key: str,
    actions: AgentSpecificationActions | None,
) -> None:
    specification = part.get("specification")
    if not isinstance(specification, Mapping):
        return
    spec = cast(Mapping[str, Any], specification)
    template = spec.get("template")
    status = spec.get("status")
    if not isinstance(template, str) or not isinstance(status, str):
        return
    spec_json = agent_specification_json(spec)

    with st.container(border=True):
        st.markdown("#### 📦 Спецификация агента")
        template_column, status_column = st.columns(2)
        with template_column:
            st.markdown(
                "**Шаблон агента**",
                help=(
                    "`one_prompt` отвечает только по инструкции или использует "
                    "Web Search; `rag` дополнительно ищет по вашим файлам."
                ),
            )
            st.code(template, language=None)
        with status_column:
            st.markdown(
                "**Готовность**",
                help=(
                    "`ready` означает, что обязательные настройки заполнены и "
                    "агента можно тестировать."
                ),
            )
            st.code(status, language=None)

        validation = spec.get("validation")
        missing_fields = None
        if isinstance(validation, Mapping):
            missing_fields = validation.get("missing_fields")
        if isinstance(missing_fields, list) and missing_fields:
            st.warning("Нужно уточнить поля: " + ", ".join(map(str, missing_fields)))

        st.download_button(
            "Скачать AgentSpecification JSON",
            data=spec_json,
            file_name="agent-specification.json",
            mime="application/json",
            key=download_key,
            help=(
                "Переносимое описание назначения, инструкции, ограничений, "
                "источников и инструментов агента. Это не готовый agent_id."
            ),
        )
        if actions is not None:
            render_agent_test_panel(
                spec,
                key_prefix=panel_key,
                actions=actions,
            )


def agent_specification_json(specification: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(specification),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def render_vector_index_result(part: Mapping[str, Any]) -> None:
    index_name = part.get("index_name")
    index_id = part.get("index_id")
    if not isinstance(index_name, str) or not isinstance(index_id, str):
        return
    with st.container(border=True):
        st.markdown("#### 🤖 Созданный векторный индекс")
        name_column, id_column = st.columns(2)
        with name_column:
            st.markdown(
                "**Имя индекса**",
                help="Понятное название базы знаний, созданной из ваших файлов.",
            )
            st.code(index_name, language=None)
        with id_column:
            st.markdown(
                "**ID индекса**",
                help=(
                    "Идентификатор Vector Store в Yandex AI Studio. File Search "
                    "использует его для поиска по загруженным файлам."
                ),
            )
            st.code(index_id, language=None)

        files = part.get("files")
        if isinstance(files, list) and files:
            st.markdown("**Файлы в индексе**")
            for number, raw_file in enumerate(files, start=1):
                if not isinstance(raw_file, Mapping):
                    continue
                file = cast(Mapping[str, Any], raw_file)
                filename = file.get("filename")
                file_id = file.get("file_id")
                if isinstance(filename, str) and isinstance(file_id, str):
                    st.text(f"{number}. {filename} (file_id: {file_id})")

        expires_after_days = part.get("expires_after_days")
        if isinstance(expires_after_days, int):
            st.caption(
                "Индекс автоматически удаляется через "
                f"{expires_after_days} день после последней активности."
            )

from collections.abc import Mapping, Sequence
from typing import Any, cast

import streamlit as st


def render_result_parts(parts: Sequence[Any]) -> None:
    for raw_part in parts:
        if not isinstance(raw_part, Mapping):
            continue
        part = cast(Mapping[str, Any], raw_part)
        kind = part.get("kind")
        if kind == "vector_index":
            render_vector_index_result(part)
        elif kind == "markdown":
            text = part.get("text")
            if isinstance(text, str) and text:
                st.markdown(text)


def render_vector_index_result(part: Mapping[str, Any]) -> None:
    index_name = part.get("index_name")
    index_id = part.get("index_id")
    if not isinstance(index_name, str) or not isinstance(index_id, str):
        return
    with st.container(border=True):
        st.markdown("#### 🤖 Созданный векторный индекс")
        name_column, id_column = st.columns(2)
        with name_column:
            st.markdown("**Имя индекса**")
            st.code(index_name, language=None)
        with id_column:
            st.markdown("**ID индекса**")
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

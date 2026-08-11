"""Render safe previews and downloads for user attachments."""

import mimetypes
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import streamlit as st

from ai_studio_agent_builder.application.interaction import AIInteraction


MAX_TEXT_PREVIEW_BYTES = 100_000
PreviewKind = Literal["image", "audio", "video", "text", "download_only", "none"]


def preview_kind_for_mime(mime_type: str) -> PreviewKind:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type == "application/pdf":
        return "download_only"
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("text/") or mime_type in {
        "application/json",
        "application/xml",
    }:
        return "text"
    return "none"


def render_attachment(
    ai_service: AIInteraction,
    user_id: str,
    attachment: Mapping[str, Any],
) -> None:
    filename = attachment.get("filename")
    if not isinstance(filename, str) or Path(filename).name != filename:
        st.warning("Файл недоступен.")
        return

    original_filename = str(attachment.get("original_filename") or filename)
    mime_type = str(
        attachment.get("mime_type")
        or mimetypes.guess_type(original_filename)[0]
        or "application/octet-stream"
    )
    path = ai_service.user_files_dir(user_id) / filename
    try:
        data = path.read_bytes()
    except OSError:
        st.warning(f"Файл «{original_filename}» больше недоступен.")
        return

    size = attachment.get("size")
    size_label = f" · {int(size):,} байт" if isinstance(size, int) else ""
    st.caption(f"📎 {original_filename}{size_label}")
    st.download_button(
        "Скачать файл",
        data=data,
        file_name=original_filename,
        mime=mime_type,
        key=f"download-{filename}",
    )
    with st.expander("Просмотреть файл"):
        render_attachment_preview(data, mime_type)


def render_attachment_preview(data: bytes, mime_type: str) -> None:
    preview_kind = preview_kind_for_mime(mime_type)
    if preview_kind == "image":
        st.image(data)
    elif preview_kind == "download_only":
        st.info(
            "Предпросмотр PDF отключён для безопасности. "
            "Скачайте файл, чтобы открыть его."
        )
    elif preview_kind == "audio":
        st.audio(data, format=mime_type)
    elif preview_kind == "video":
        st.video(data, format=mime_type)
    elif preview_kind == "text":
        preview = data[:MAX_TEXT_PREVIEW_BYTES].decode("utf-8", errors="replace")
        st.code(preview)
        if len(data) > MAX_TEXT_PREVIEW_BYTES:
            st.caption("Показаны первые 100 000 байт. Полную версию можно скачать.")
    else:
        st.info(
            "Предпросмотр для этого формата недоступен. "
            "Скачайте файл, чтобы открыть его."
        )

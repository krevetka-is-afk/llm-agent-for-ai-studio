import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest
from aiogram import Bot
from aiogram.types import ContentType, Message

import ai_studio_agent_builder.presentation.telegram.media as media
from ai_studio_agent_builder.application.interaction import UploadValidationError
from ai_studio_agent_builder.presentation.telegram.media import (
    download_media,
    sanitize_download_filename,
)


def test_telegram_filename_is_reduced_to_a_safe_basename() -> None:
    assert sanitize_download_filename("..\\..// bad:\x00name?.txt ") == "bad_name_.txt"
    assert sanitize_download_filename("../..") == "download.bin"


class _FakeBot:
    def __init__(self, payload: bytes, *, provider_size: int | None = None) -> None:
        self.payload = payload
        self.provider_size = provider_size
        self.get_file_calls = 0

    async def get_file(self, file_id: str) -> SimpleNamespace:
        self.get_file_calls += 1
        assert file_id == "telegram-file"
        return SimpleNamespace(file_path="remote/path", file_size=self.provider_size)

    async def download_file(
        self,
        file_path: str,
        *,
        destination: Any,
        seek: bool,
    ) -> None:
        assert file_path == "remote/path"
        assert seek is False
        for offset in range(0, len(self.payload), 3):
            destination.write(self.payload[offset : offset + 3])
            destination.flush()


def _document_message(*, declared_size: int | None) -> SimpleNamespace:
    return SimpleNamespace(
        content_type=ContentType.DOCUMENT,
        message_id=7,
        document=SimpleNamespace(
            file_id="telegram-file",
            file_name="../report.csv",
            file_size=declared_size,
        ),
    )


def test_download_media_rejects_declared_oversize_before_provider_download(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(media, "MAX_UPLOAD_BYTES", 4)
    bot = _FakeBot(b"data")

    with pytest.raises(UploadValidationError):
        asyncio.run(
            download_media(
                cast(Bot, bot),
                cast(Message, _document_message(declared_size=5)),
                tmp_path,
            )
        )

    assert bot.get_file_calls == 0
    assert list(tmp_path.glob("*")) == []


def test_download_media_enforces_stream_limit_and_removes_partial_file(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(media, "MAX_UPLOAD_BYTES", 4)
    bot = _FakeBot(b"too-large")

    with pytest.raises(UploadValidationError):
        asyncio.run(
            download_media(
                cast(Bot, bot),
                cast(Message, _document_message(declared_size=None)),
                tmp_path,
            )
        )

    assert list(tmp_path.glob("*")) == []


def test_download_media_streams_to_an_atomic_sanitized_target(tmp_path) -> None:
    bot = _FakeBot(b"a,b\n1,2\n", provider_size=8)

    filename = asyncio.run(
        download_media(
            cast(Bot, bot),
            cast(Message, _document_message(declared_size=8)),
            tmp_path,
        )
    )

    assert filename == "report.csv"
    assert (tmp_path / filename).read_bytes() == b"a,b\n1,2\n"
    assert list(tmp_path.glob("*.partial")) == []

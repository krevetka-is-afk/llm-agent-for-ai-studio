import asyncio
import logging
import os
import stat
from pathlib import Path

import pytest

import ai_studio_agent_builder.infrastructure.persistence.local_attachments as local_attachments
from ai_studio_agent_builder.application.file_policy import UnsafeUploadPathError
from ai_studio_agent_builder.application.interaction import UploadValidationError
from ai_studio_agent_builder.application.ports.generated_artifact_store import (
    GeneratedArtifactTooLargeError,
)
from ai_studio_agent_builder.infrastructure.persistence.local_attachments import (
    GENERATED_ARTIFACTS_DIRECTORY,
    LocalAttachmentStore,
)


def test_attachment_store_rejects_storage_scope_escape(tmp_path: Path) -> None:
    store = LocalAttachmentStore(tmp_path / "uploads")

    with pytest.raises(UnsafeUploadPathError):
        store.save("../outside", "secret.txt", b"secret")

    with pytest.raises(UnsafeUploadPathError):
        asyncio.run(store.clear("../outside"))

    assert not (tmp_path / "outside").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode unavailable")
def test_attachment_store_restricts_user_directory_and_file_permissions(
    tmp_path: Path,
) -> None:
    store = LocalAttachmentStore(tmp_path)

    attachment = store.save("user-1", "private.txt", b"private")

    user_dir = store.directory_for("user-1")
    assert stat.S_IMODE(user_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((user_dir / attachment.filename).stat().st_mode) == 0o600


def test_attachment_store_enforces_accumulated_user_quota(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(local_attachments, "MAX_USER_STORAGE_BYTES", 5)
    store = LocalAttachmentStore(tmp_path)
    store.save("user-1", "first.txt", b"1234")

    with pytest.raises(UploadValidationError, match="storage byte limit"):
        store.save("user-1", "second.txt", b"56")


def test_generated_artifact_store_enforces_application_storage_quota(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(local_attachments, "MAX_TOTAL_STORAGE_BYTES", 5)
    store = LocalAttachmentStore(tmp_path)
    store.save("user-1", "first.txt", b"1234")

    with pytest.raises(GeneratedArtifactTooLargeError, match="storage quota"):
        store.save_generated_artifact(
            "user-2",
            "result.txt",
            (b"56",),
            max_bytes=10,
        )


def test_generated_artifact_store_normalizes_names_without_overwriting(tmp_path: Path):
    store = LocalAttachmentStore(tmp_path)

    first = store.save_generated_artifact(
        "user-1",
        "../result.csv",
        (b"first",),
        max_bytes=100,
    )
    second = store.save_generated_artifact(
        "user-1",
        "../result.csv",
        (b"second",),
        max_bytes=100,
    )

    assert first.display_name == "result.csv"
    assert second.display_name == "result.csv"
    assert first.local_name != second.local_name
    assert store.read_generated_artifact("user-1", first.local_name) == b"first"
    assert store.read_generated_artifact("user-1", second.local_name) == b"second"


def test_generated_artifact_store_removes_partial_file_on_stream_limit(tmp_path: Path):
    store = LocalAttachmentStore(tmp_path)

    with pytest.raises(GeneratedArtifactTooLargeError):
        store.save_generated_artifact(
            "user-1",
            "large.bin",
            (b"123", b"456"),
            max_bytes=5,
        )

    generated_dir = tmp_path / "user-1" / GENERATED_ARTIFACTS_DIRECTORY
    assert list(generated_dir.iterdir()) == []


def test_generated_artifact_store_rejects_untrusted_local_handle(tmp_path: Path):
    store = LocalAttachmentStore(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(UnsafeUploadPathError):
        store.read_generated_artifact("user-1", "../outside.txt")


def test_generated_artifact_store_records_best_effort_stream_close_failure(
    tmp_path: Path, caplog
):
    class CloseFailureIterator:
        def __init__(self) -> None:
            self._chunks = iter((b"result",))

        def __iter__(self):
            return self

        def __next__(self) -> bytes:
            return next(self._chunks)

        def close(self) -> None:
            raise RuntimeError("synthetic close failure")

    store = LocalAttachmentStore(tmp_path)

    with caplog.at_level(logging.DEBUG):
        stored = store.save_generated_artifact(
            "user-1",
            "result.csv",
            CloseFailureIterator(),
            max_bytes=100,
        )

    assert store.read_generated_artifact("user-1", stored.local_name) == b"result"
    assert "Could not close generated artifact stream" in caplog.text


def test_generated_artifact_store_clears_user_outputs(tmp_path: Path):
    store = LocalAttachmentStore(tmp_path)
    stored = store.save_generated_artifact(
        "user-1",
        "result.csv",
        (b"result",),
        max_bytes=100,
    )

    asyncio.run(store.clear_generated_artifacts("user-1"))

    with pytest.raises(FileNotFoundError):
        store.read_generated_artifact("user-1", stored.local_name)

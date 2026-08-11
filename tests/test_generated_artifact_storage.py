import asyncio
from pathlib import Path

import pytest

from ai_studio_agent_builder.application.file_policy import UnsafeUploadPathError
from ai_studio_agent_builder.application.ports.generated_artifact_store import (
    GeneratedArtifactTooLargeError,
)
from ai_studio_agent_builder.infrastructure.persistence.local_attachments import (
    GENERATED_ARTIFACTS_DIRECTORY,
    LocalAttachmentStore,
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

import pytest
from typing import BinaryIO

import ai_studio_agent_builder.infrastructure.yandex_ai_studio.files_gateway as files_gateway_module
from ai_studio_agent_builder.application.file_policy import (
    MAX_UPLOAD_BYTES,
    UnsafeUploadPathError,
    UploadTooLargeError,
    resolve_upload_path,
)
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.files_gateway import (
    YandexFileResourceGateway,
    upload_local_file,
)
from ai_studio_agent_builder.builder.agents.rag_agent import (
    RAG_AGENT_INSTRUCTIONS,
    RAG_TOOLS_SETUP,
)


class _FakeFilesClient:
    def __init__(self) -> None:
        self.created: list[bytes] = []
        self.purposes: list[str] = []
        self.deleted: list[str] = []

    def create(self, *, file: BinaryIO, purpose: str):
        self.purposes.append(purpose)
        self.created.append(file.read())
        return type("UploadedFile", (), {"id": "file-safe"})()

    def delete(self, file_id: str):
        self.deleted.append(file_id)


class _FakeClient:
    def __init__(self) -> None:
        self.files: _FakeFilesClient = _FakeFilesClient()


def test_upload_local_file_rejects_absolute_and_parent_paths(tmp_path):
    (tmp_path / "safe.txt").write_text("safe")

    with pytest.raises(UnsafeUploadPathError):
        resolve_upload_path(tmp_path, "/etc/passwd")

    with pytest.raises(UnsafeUploadPathError):
        resolve_upload_path(tmp_path, "../safe.txt")


def test_upload_local_file_rejects_previews_directory(tmp_path):
    preview_dir = tmp_path / ".previews"
    preview_dir.mkdir()
    (preview_dir / "page.png").write_bytes(b"preview")

    with pytest.raises(UnsafeUploadPathError):
        resolve_upload_path(tmp_path, ".previews/page.png")


def test_upload_local_file_rejects_symlink_components(tmp_path):
    outside = tmp_path.parent / "outside-upload-target.txt"
    outside.write_text("secret")
    (tmp_path / "linked.txt").symlink_to(outside)

    with pytest.raises(UnsafeUploadPathError):
        resolve_upload_path(tmp_path, "linked.txt")


def test_upload_local_file_uploads_only_valid_regular_file(tmp_path):
    (tmp_path / "safe.txt").write_bytes(b"safe")
    client = _FakeClient()

    file_id = upload_local_file(client, tmp_path, "safe.txt")

    assert file_id == "file-safe"
    assert client.files.created == [b"safe"]
    assert client.files.purposes == ["assistants"]


def test_upload_local_file_enforces_size_limit(tmp_path):
    (tmp_path / "huge.bin").write_bytes(b"x" * (MAX_UPLOAD_BYTES + 1))

    with pytest.raises(UploadTooLargeError):
        upload_local_file(_FakeClient(), tmp_path, "huge.bin")


def test_code_interpreter_gateway_uses_user_data_and_deletes_remote_file(tmp_path):
    (tmp_path / "input.csv").write_bytes(b"value\n1\n")
    client = _FakeClient()
    gateway = YandexFileResourceGateway(client)

    file_id = gateway.upload_user_file(tmp_path, "input.csv")
    gateway.delete_file(file_id)

    assert client.files.purposes == ["user_data"]
    assert client.files.deleted == ["file-safe"]


def test_rag_agent_has_no_model_facing_upload_file_tool():
    tool_names = {getattr(tool, "name", None) for tool in RAG_TOOLS_SETUP}

    assert tool_names == {
        "create_search_index",
        "update_agent_specification",
        "finalize_agent_specification",
        "finish_dialog",
    }
    assert "upload_file" not in RAG_AGENT_INSTRUCTIONS
    assert not hasattr(files_gateway_module, "upload_file")

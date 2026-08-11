from pathlib import Path
from typing import Any, BinaryIO, Protocol

from ...application.file_policy import enforce_upload_size, resolve_upload_path


class _FilesResource(Protocol):
    def create(self, *, file: BinaryIO, purpose: str) -> Any: ...


class _UploadClient(Protocol):
    @property
    def files(self) -> _FilesResource: ...


def upload_local_file(client: _UploadClient, base_dir: Path, filename: str) -> str:
    """Upload one policy-validated local file and return its provider file ID."""
    path = resolve_upload_path(base_dir, filename)
    enforce_upload_size(path, source_name=filename)
    with path.open("rb") as file:
        uploaded_file = client.files.create(file=file, purpose="assistants")
    return uploaded_file.id

import logging
from pathlib import Path
from typing import Any, BinaryIO, Protocol

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
"""Maximum bytes accepted for one uploaded file before sending it to AI Studio."""


class UnsafeUploadPathError(ValueError):
    """Raised when a saved upload path escapes the current request sandbox."""


class UploadTooLargeError(ValueError):
    """Raised when a saved upload exceeds the documented per-file limit."""


class _FilesResource(Protocol):
    def create(self, *, file: BinaryIO, purpose: str) -> Any: ...


class _UploadClient(Protocol):
    @property
    def files(self) -> _FilesResource: ...


def upload_local_file(client: _UploadClient, base_dir: Path, filename: str) -> str:
    """Upload one validated, saved user file and return its AI Studio file id.

    The model never chooses this path. The service passes only filenames from the
    current request after pre-upload validation. Filenames must be relative,
    resolve inside ``base_dir``, avoid ``.previews`` folders, and contain no
    symlink path components.
    """
    path = resolve_upload_path(base_dir, filename)
    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise UploadTooLargeError(
            f"Upload {filename!r} is {size} bytes; limit is {MAX_UPLOAD_BYTES} bytes"
        )
    with path.open("rb") as file:
        uploaded_file = client.files.create(file=file, purpose="assistants")
    return uploaded_file.id


def resolve_upload_path(base_dir: Path, filename: str) -> Path:
    """Return the canonical upload path or raise on traversal/symlink access."""
    requested = Path(filename)
    if requested.is_absolute() or ".." in requested.parts:
        raise UnsafeUploadPathError("Upload filename must be relative to the user dir")
    if ".previews" in requested.parts:
        raise UnsafeUploadPathError("Preview artifacts are not valid upload sources")
    if requested.name in {"", ".", ".."}:
        raise UnsafeUploadPathError("Upload filename is empty or reserved")

    base = base_dir.resolve(strict=False)
    candidate = base / requested
    cursor = base
    for part in requested.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise UnsafeUploadPathError("Symlink upload paths are not allowed")

    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise UnsafeUploadPathError("Upload path escapes the user dir") from exc
    if not resolved.is_file():
        raise UnsafeUploadPathError("Upload path must reference a regular file")
    return resolved

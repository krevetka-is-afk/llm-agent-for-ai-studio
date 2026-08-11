import re
from pathlib import Path


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
"""Maximum bytes accepted for one uploaded file before provider upload."""

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")


class UnsafeUploadPathError(ValueError):
    """Raised when a saved upload path escapes the current request sandbox."""


class UploadTooLargeError(ValueError):
    """Raised when a saved upload exceeds the documented per-file limit."""


def sanitize_filename(original_filename: str, *, fallback: str) -> str:
    basename = Path(original_filename.replace("\\", "/")).name
    safe_filename = _UNSAFE_FILENAME_CHARS.sub("_", basename).strip(" .")
    if safe_filename in {"", ".", ".."}:
        return fallback
    return safe_filename


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


def enforce_upload_size(
    path: Path,
    *,
    source_name: str | None = None,
    limit: int = MAX_UPLOAD_BYTES,
) -> None:
    size = path.stat().st_size
    if size > limit:
        raise UploadTooLargeError(
            f"Upload {source_name or path.name!r} is {size} bytes; "
            f"limit is {limit} bytes"
        )

"""Compatibility imports for file policy and the Yandex Files adapter.

New code must import the packaged modules directly. This module is removed before
the public ``v0.1.0`` release.
"""

from ai_studio_agent_builder.application.file_policy import (
    MAX_UPLOAD_BYTES,
    UnsafeUploadPathError,
    UploadTooLargeError,
    resolve_upload_path,
)
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.files_gateway import (
    upload_local_file,
)

__all__ = [
    "MAX_UPLOAD_BYTES",
    "UnsafeUploadPathError",
    "UploadTooLargeError",
    "resolve_upload_path",
    "upload_local_file",
]

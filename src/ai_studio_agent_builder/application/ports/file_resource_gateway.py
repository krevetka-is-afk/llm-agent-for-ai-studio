"""Provider boundary for temporary files used by generated-agent previews."""

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from ai_studio_agent_builder.application.dto import AIStudioCredentials


class FileResourceGateway(Protocol):
    def upload_user_file(self, base_dir: Path, filename: str) -> str: ...

    def iter_file_bytes(
        self,
        file_id: str,
        *,
        chunk_size: int,
    ) -> Iterator[bytes]: ...

    def delete_file(self, file_id: str) -> None: ...

    def delete_container(self, container_id: str) -> None: ...


class FileResourceGatewayFactory(Protocol):
    def create(self, credentials: AIStudioCredentials) -> FileResourceGateway: ...


__all__ = ["FileResourceGateway", "FileResourceGatewayFactory"]

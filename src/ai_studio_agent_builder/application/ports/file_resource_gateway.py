"""Provider boundary for temporary files used by generated-agent previews."""

from pathlib import Path
from typing import Protocol

from ai_studio_agent_builder.application.dto import AIStudioCredentials


class FileResourceGateway(Protocol):
    def upload_user_file(self, base_dir: Path, filename: str) -> str: ...

    def delete_file(self, file_id: str) -> None: ...


class FileResourceGatewayFactory(Protocol):
    def create(self, credentials: AIStudioCredentials) -> FileResourceGateway: ...


__all__ = ["FileResourceGateway", "FileResourceGatewayFactory"]

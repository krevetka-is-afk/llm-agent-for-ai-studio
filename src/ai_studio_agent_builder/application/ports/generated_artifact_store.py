"""Persistence boundary for bounded generated-agent artifacts."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredGeneratedArtifact:
    local_name: str
    display_name: str
    size_bytes: int


class GeneratedArtifactTooLargeError(ValueError):
    """Raised after a generated artifact crosses its streaming byte limit."""


class GeneratedArtifactStore(Protocol):
    def save_generated_artifact(
        self,
        user_id: str,
        display_name: str,
        chunks: Iterable[bytes],
        *,
        max_bytes: int,
    ) -> StoredGeneratedArtifact: ...

    def read_generated_artifact(self, user_id: str, local_name: str) -> bytes: ...

    async def clear_generated_artifacts(self, user_id: str) -> None: ...


__all__ = [
    "GeneratedArtifactStore",
    "GeneratedArtifactTooLargeError",
    "StoredGeneratedArtifact",
]

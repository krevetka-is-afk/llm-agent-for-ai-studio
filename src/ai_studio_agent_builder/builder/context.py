from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..application.builder_state import ConversationState


class BuilderResourceClient(Protocol):
    """Least-privilege resources exposed to builder tools for one request."""

    @property
    def files(self) -> Any: ...

    @property
    def vector_stores(self) -> Any: ...


@dataclass
class RequestContext:
    user_id: str
    request_id: str
    user_files_dir: Path
    client: BuilderResourceClient
    state: ConversationState
    folder_id: str
    allowed_file_ids: frozenset[str] = frozenset()
    filenames_by_file_id: dict[str, str] = field(default_factory=dict)


__all__ = ["BuilderResourceClient", "RequestContext"]

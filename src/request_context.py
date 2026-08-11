from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from ai_studio_agent_builder.application.builder_state import ConversationState


@dataclass
class RequestContext:
    user_id: str
    request_id: str
    user_files_dir: Path
    client: OpenAI
    state: ConversationState
    folder_id: str
    allowed_file_ids: frozenset[str] = frozenset()
    filenames_by_file_id: dict[str, str] = field(default_factory=dict)

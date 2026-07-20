from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from conversation_state import ConversationState


@dataclass
class RequestContext:
    user_id: str
    request_id: str
    user_files_dir: Path
    client: OpenAI
    state: ConversationState
    folder_id: str
    allowed_file_ids: frozenset[str] = frozenset()

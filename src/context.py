from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from chatkit.types import ThreadMetadata
from openai import OpenAI


class ConversationState:
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir.resolve()
        self._is_done = False

    def set_done(self) -> None:
        self._is_done = True

    def is_done(self) -> bool:
        return self._is_done

    def get_base_dir(self) -> Path:
        return self._base_dir


class RequestContext(TypedDict):
    conv_context: ConversationState
    client: OpenAI


@dataclass
class AppContext:
    user_id: str
    thread: ThreadMetadata
    request_context: RequestContext
    is_done: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.is_done = self.request_context["conv_context"].is_done()

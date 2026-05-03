from dataclasses import dataclass
from openai import OpenAI
from pathlib import Path

@dataclass
class AppContext:
    user_id: str
    client: OpenAI
    base_dir: Path
    is_done: bool = False
import logging
from pathlib import Path

from agents import RunContextWrapper, function_tool

from chatkit.agents import AgentContext


def local_path(path: str) -> Path:
    return Path(__file__).parent / path


@function_tool
def upload_file(ctx: RunContextWrapper[AgentContext], filename: str) -> str:
    """
    Upload a file to storage by its name.
    Returns a file ID that must be saved for later use in create_vector_index.
    """
    logging.info(f"Загружаем файл {filename}...")

    client = ctx.context.request_context['client']

    f = client.files.create(
        file=open(local_path(filename), "rb"),
        purpose="assistants",
    )
    logging.info(f"Файл {filename} загружен: {f.id}")

    return f.id

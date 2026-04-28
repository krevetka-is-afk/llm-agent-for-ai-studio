import logging
from pathlib import Path
from openai import OpenAI

from agents import RunContextWrapper, function_tool

from chatkit.agents import AgentContext


@function_tool
def upload_file(ctx: RunContextWrapper[AgentContext], filename: str) -> str:
    """
    Upload a file to storage by its name.
    Returns a file ID that must be saved for later use in create_vector_index.
    """
    logging.info(f"Загружаем файл {filename}...")

    client: OpenAI = ctx.context.request_context['client']
    base_dir: Path = ctx.context.request_context['conv_context'].get_base_dir()

    path = base_dir / filename
    f = client.files.create(
        file=open(path, "rb"),
        purpose="assistants",
    )
    logging.info(f"Файл {filename} загружен: {f.id}")

    return f.id

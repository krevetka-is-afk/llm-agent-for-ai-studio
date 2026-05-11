import logging
from pathlib import Path
from openai import OpenAI

from agents import RunContextWrapper, function_tool

from chatkit.agents import AgentContext

from ..logging_config import bind_logger

logger = logging.getLogger(__name__)


@function_tool
def upload_file(ctx: RunContextWrapper[AgentContext], filename: str) -> str:
    """
    Upload a file to storage by its name.
    Returns a file ID that must be saved for later use in create_vector_index.
    """
    tool_logger = bind_logger(logger, thread_id=ctx.context.thread.id)
    tool_logger.info("Загружаем файл %s", filename)

    client: OpenAI = ctx.context.request_context['client']
    base_dir: Path = ctx.context.request_context['conv_context'].get_base_dir()

    path = base_dir / filename
    f = client.files.create(
        file=open(path, "rb"),
        purpose="assistants",
    )
    tool_logger.info("Файл %s загружен: %s", filename, f.id)

    return f.id

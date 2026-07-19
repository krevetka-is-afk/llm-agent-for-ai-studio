import logging
from pathlib import Path
from openai import OpenAI

from agents import RunContextWrapper, function_tool

from context import RequestContext

from logging_config import bind_logger

logger = logging.getLogger(__name__)


def upload_local_file(client: OpenAI, base_dir: Path, filename: str) -> str:
    """Upload a saved user file and return its AI Studio file identifier."""
    path = base_dir / filename
    with path.open("rb") as file:
        uploaded_file = client.files.create(file=file, purpose="assistants")
    return uploaded_file.id


@function_tool
def upload_file(ctx: RunContextWrapper[RequestContext], filename: str) -> str:
    """
    Upload a file to storage by its name.
    Returns a file ID that must be saved for later use in create_search_index.
    """
    tool_logger = bind_logger(logger, user_id=ctx.context.user_id)
    tool_logger.info("Загружаем файл %s", filename)

    client: OpenAI = ctx.context.client
    base_dir: Path = ctx.context.user_files_dir

    file_id = upload_local_file(client, base_dir, filename)
    tool_logger.info("Файл %s загружен: %s", filename, file_id)

    return file_id

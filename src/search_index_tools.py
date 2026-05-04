import json
import logging
import time

from agents import RunContextWrapper, function_tool
from chatkit.agents import AgentContext
from openai import OpenAI
from openai.types import vector_store_create_params, StaticFileChunkingStrategyObjectParam, \
    StaticFileChunkingStrategyParam

from .logging_config import bind_logger

logger = logging.getLogger(__name__)

DEFAULT_CHUNKING_STRATEGY = StaticFileChunkingStrategyObjectParam(
    type="static",
    static=StaticFileChunkingStrategyParam(
        max_chunk_size_tokens=1408, chunk_overlap_tokens=148)
)


def _tool_logger(ctx: RunContextWrapper[AgentContext]) -> logging.LoggerAdapter:
    return bind_logger(logger, thread_id=ctx.context.thread.id)


@function_tool
def create_search_index(ctx: RunContextWrapper[AgentContext], file_ids: list[str], vector_store_name: str) -> str:
    """
    Build a vector store from the provided files.

    Args:
        name: Human-readable name for the vector store.
        file_ids: List of file ids to include in the vector store.

    Returns:
        The ID of the created vector store.
    """
    tool_logger = _tool_logger(ctx)
    tool_logger.info("Создаем поисковый индекс с %s файлами", len(file_ids))

    client: OpenAI = ctx.context.request_context['client']
    vector_store = client.vector_stores.create(
        name=vector_store_name,
        metadata={"key": "value"},
        expires_after=vector_store_create_params.ExpiresAfter(anchor="last_active_at", days=1),
        chunking_strategy=DEFAULT_CHUNKING_STRATEGY,
        file_ids=file_ids,
    )
    vector_store_id = vector_store.id
    tool_logger.info("Vector Store создан: %s", vector_store_id)

    while True:
        vector_store = client.vector_stores.retrieve(vector_store_id)
        if vector_store.status == "completed":
            break
        tool_logger.debug("Vector Store %s status=%s; waiting", vector_store_id, vector_store.status)
        time.sleep(3)

    tool_logger.info("Vector Store %s готов к работе", vector_store_id)

    return vector_store_id


@function_tool
def upload_vector_store_file(ctx: RunContextWrapper[AgentContext], vector_store_id: str, file_id: str):
    """
    Attaching a File to a vector store.

    Args:
        vector_store_id: The id of vector store
        file_id: The id of file to upload to vector store
    """
    tool_logger = _tool_logger(ctx)
    tool_logger.info("Добавляем файл %s в индекс %s", file_id, vector_store_id)

    client: OpenAI = ctx.context.request_context['client']
    response = client.vector_stores.files.create(
        vector_store_id=vector_store_id,
        file_id=file_id,
        chunking_strategy=DEFAULT_CHUNKING_STRATEGY,
    )

    tool_logger.info("Добавление файла в индекс завершено")
    print(response)
    if response is not None:
        return "Файл успешно добавлен в индекс"
    return "Не получилось добавить файл в индекса"


@function_tool
def delete_vector_store_file(ctx: RunContextWrapper[AgentContext], vector_store_id: str, file_id: str):
    """
    Delete a vector store file. This will remove the file from the vector store but the file itself will not be deleted.

    Args:
        vector_store_id: The id of vector store
        file_id: The id of file to remove from vector store
    """
    tool_logger = _tool_logger(ctx)
    tool_logger.info("Удаляем файл %s из индекса %s", file_id, vector_store_id)

    client: OpenAI = ctx.context.request_context['client']
    response = client.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)

    tool_logger.info("Удаление файла из индекса завершено")
    if response.deleted:
        return "Файл успешно удален из индекса"
    return "Не получилось удалить файл из индекса"


@function_tool
def search_in_vector_index(ctx: RunContextWrapper[AgentContext], vector_store_id: str, query: str):
    """
    Search the vector store for relevant information based on a text query.

    Args:
        vector_store_id: The id of vector store
        query: The text query to search for in the vector store
    """
    tool_logger = _tool_logger(ctx)
    tool_logger.info("Ищем по запросу длиной %s в индексе %s", len(query), vector_store_id)

    client: OpenAI = ctx.context.request_context['client']
    response = client.vector_stores.search(vector_store_id, query=query)

    results = [content.content[0].text for content in response.data]

    tool_logger.info("Поиск по индексу %s завершен", vector_store_id)
    return json.dumps(results)

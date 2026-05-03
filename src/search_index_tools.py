import json
import logging
import time

from agents import RunContextWrapper, function_tool
from .context import AppContext
from openai import OpenAI


@function_tool
def create_search_index(
    ctx: RunContextWrapper[AppContext], file_ids: list[str], vector_store_name: str
) -> str:
    """
    Build a vector store from the provided files.

    Args:
        name: Human-readable name for the vector store.
        file_ids: List of file ids to include in the vector store.

    Returns:
        The ID of the created vector store.
    """
    logging.info("Создаем поисковый индекс...")

    client: OpenAI = ctx.context.client
    vector_store = client.vector_stores.create(
        name=vector_store_name,
        metadata={"key": "value"},
        expires_after={"anchor": "last_active_at", "days": 1},
        chunking_strategy={
            "type": "static",
            "static": {
                "max_chunk_size_tokens": 1408,
                "chunk_overlap_tokens": 148,
            },
        },
        file_ids=file_ids,
    )
    vector_store_id = vector_store.id
    logging.info(f"Vector Store создан: {vector_store_id}")

    while True:
        vector_store = client.vector_stores.retrieve(vector_store_id)
        if vector_store.status == "completed":
            break
        time.sleep(3)

    logging.info("Vector Store готов к работе.")

    return vector_store_id


@function_tool
def upload_vector_store_file(
    ctx: RunContextWrapper[AppContext], vector_store_id: str, file_id: str
):
    """
    Attaching a File to a vector store.

    Args:
        vector_store_id: The id of vector store
        file_id: The id of file to upload to vector store
    """
    logging.info(f"Добавляем файл: {file_id} в индекса {vector_store_id}")

    client: OpenAI = ctx.context.client
    response = client.vector_stores.files.create(
        vector_store_id=vector_store_id,
        file_id=file_id,
        chunking_strategy={
            "type": "static",
            "static": {
                "max_chunk_size_tokens": 1408,
                "chunk_overlap_tokens": 148,
            },
        },
    )

    logging.info("Добавление файла завершено")
    print(response)
    if response is not None:
        return "Файл успешно добавлен в индекс"
    return "Не получилось добавить файл в индекса"


@function_tool
def delete_vector_store_file(
    ctx: RunContextWrapper[AppContext], vector_store_id: str, file_id: str
):
    """
    Delete a vector store file. This will remove the file from the vector store but the file itself will not be deleted.

    Args:
        vector_store_id: The id of vector store
        file_id: The id of file to remove from vector store
    """
    logging.info(f"Удаляем файл: {file_id} из индекса {vector_store_id}")

    client: OpenAI = ctx.context.client
    response = client.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)

    logging.info("Удаление завершено")
    if response.deleted:
        return "Файл успешно удален из индекса"
    return "Не получилось удалить файл из индекса"


@function_tool
def search_in_vector_index(ctx: RunContextWrapper[AppContext], vector_store_id: str, query: str):
    """
    Search the vector store for relevant information based on a text query.

    Args:
        vector_store_id: The id of vector store
        query: The text query to search for in the vector store
    """
    logging.info(f"Ищем по запросу: {query} в индексе {vector_store_id}")

    client: OpenAI = ctx.context.client
    response = client.vector_stores.search(vector_store_id, query=query)

    results = [content.content[0].text for content in response.data]

    logging.info("Поиск завершен")
    return json.dumps(results)

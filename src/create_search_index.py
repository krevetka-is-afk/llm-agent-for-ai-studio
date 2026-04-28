import logging
import time

from agents import RunContextWrapper, function_tool
from chatkit.agents import AgentContext


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
    logging.info("Создаем поисковый индекс...")

    client = ctx.context.request_context['client']
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

import json
import logging

from agents import RunContextWrapper, function_tool
from chatkit.agents import AgentContext
from openai import OpenAI


@function_tool
def search_in_vector_index(ctx: RunContextWrapper[AgentContext], vector_store_id: str, query: str):
    """
    Search the vector store for relevant information based on a text query.

    Args:
        vector_store_id: The id of vector store
        query: The text query to search for in the vector store
    """
    logging.info(f"Ищем по запросу: {query} в индексе {vector_store_id}")

    client: OpenAI = ctx.context.request_context['client']
    response = client.vector_stores.search(vector_store_id, query=query)

    results = [content.content[0].text for content in response.data]

    logging.info("Поиск завершен")
    return json.dumps(results)

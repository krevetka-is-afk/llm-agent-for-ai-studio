from langchain_core.utils.function_calling import convert_to_openai_tool


def build_vector_store_tool(name: str, files: list[str]) -> str:
    """
    Build a vector store from the provided files.

    Args:
        name: Human-readable name for the vector store.
        files: List of file paths to upload and index in the vector store.

    Returns:
        The ID of the created vector store.
    """


def search_vector_store_tool(vector_store_id: str, query: str, limit: int) -> list[str]:
    """
    Search an existing vector store using a natural language query.

    Args:
        vector_store_id: ID of the vector store to search.
        query: Text describing what to find.
        limit: Limit of results count

    Returns:
        List of relevant search results as a strings.
    """


RAG_TOOLS_SCHEMA = [
    convert_to_openai_tool(build_vector_store_tool),
    convert_to_openai_tool(search_vector_store_tool),
]

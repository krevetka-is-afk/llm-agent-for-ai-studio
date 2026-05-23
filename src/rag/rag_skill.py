from typing import Any, AsyncIterator

from config import Settings
from context import RequestContext
from engine_skill import EngineCard
from rag.rag_agent_server import RagServer


RAG_ENGINE_CARD = EngineCard(
    skill_id="rag",
    name="RAG search skill",
    description=(
        "Creates vector search indexes from uploaded files and searches them to answer "
        "user questions."
    ),
    tags=(
        "rag",
        "files",
        "vector-store",
        "search",
    ),
    examples=(
        "Create a search index from this file.",
        "Find the answer in my uploaded documents.",
        "Search this vector store for relevant information.",
    ),
    tools=(
        "upload_file",
        "create_search_index",
        "search_in_vector_index",
        "upload_vector_store_file",
        "delete_vector_store_file",
        "finish_dialog",
    ),
)


class RagEngineSkill:
    card = RAG_ENGINE_CARD

    def __init__(self, settings: Settings, server: RagServer | None = None):
        self._server = server or RagServer(settings)

    async def respond(
        self,
        input_user_message: str,
        context: RequestContext,
    ) -> AsyncIterator[Any]:
        async for event in self._server.respond(
            input_user_message=input_user_message,
            context=context,
        ):
            yield event

import logging
from typing import Any, AsyncIterator

from openai import OpenAI

from .config import Settings
from .context import AppContext
from .rag_agent import RAGAgent
from .session import get_session

DEFAULT_THREAD_ID = "demo_default_thread"


class RagServer:
    def __init__(self, settings: Settings, client: OpenAI):
        self.client = client
        self.agent = RAGAgent(settings)

    async def respond(
        self,
        input_user_message: str | None,
        context: AppContext,
    ) -> AsyncIterator[Any]:
        if input_user_message is None:
            return

        user_message = input_user_message
        logging.info(f"{user_message=}")
        session = get_session(context.user_id)
        agent_context = context

        result = self.agent.invoke(
            user_message,
            agent_context,
            session,
        )

        async for event in result.stream_events():
            yield event

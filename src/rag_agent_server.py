import logging
from typing import Any, AsyncIterator

from openai import OpenAI

from .config import Settings
from .context import AppContext
from .logging_config import bind_logger
from .rag_agent import RAGAgent
from .session import get_session

DEFAULT_THREAD_ID = "demo_default_thread"

logger = logging.getLogger(__name__)


class RagServer:
    def __init__(self, settings: Settings, client: OpenAI):
        self.client = client
        self.agent = RAGAgent(settings)

    async def respond(
            self,
            input_user_message: str,
            context: AppContext,
    ) -> AsyncIterator[Any]:
        if not input_user_message.strip():
            return

        request_logger = bind_logger(
            logger,
            thread_id=context.thread.id,
        )
        request_logger.info("Invoking agent with %s chars of user input", len(input_user_message))
        session = get_session(context.user_id)

        result = self.agent.invoke(
            input_user_message,
            context,
            session,
        )

        async for event in result.stream_events():
            yield event

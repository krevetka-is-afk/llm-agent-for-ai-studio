import logging
from typing import Any, AsyncIterator

from openai import OpenAI

from ..config import Settings
from ..context import RequestContext
from ..logging_config import bind_logger
from .rag_agent import RAGAgent
from ..session import get_session


logger = logging.getLogger(__name__)


class RagServer:
    def __init__(self, settings: Settings):
        self.db_path = settings.db_path
        self.agent = RAGAgent(settings)

    async def respond(
        self,
        input_user_message: str,
        context: RequestContext,
    ) -> AsyncIterator[Any]:
        if not input_user_message.strip():
            return

        request_logger = bind_logger(
            logger,
            user_id=context.user_id,
        )
        request_logger.info(
            "Invoking agent with %s chars of user input", len(input_user_message)
        )
        session = get_session(context.user_id, self.db_path)

        result = self.agent.invoke(
            input_user_message,
            context,
            session,
        )

        async for event in result.stream_events():
            yield event

import logging
from typing import Any, AsyncIterator

from config import AIStudioAuth, SessionDBConfig, ModelConfig, ConnectionConfig
from context import RequestContext
from logging_config import bind_logger
from session import get_session
from rag.rag_agent import RAGAgent


logger = logging.getLogger(__name__)


class RagServer:
    def __init__(self, auth_config: AIStudioAuth, session_db_config: SessionDBConfig, model_config: ModelConfig, connection_config: ConnectionConfig):
        self.db_path = session_db_config.path
        self.agent = RAGAgent(auth_config, model_config, connection_config)

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

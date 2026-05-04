import logging
from typing import Any, AsyncIterator, Optional

from chatkit.agents import AgentContext, stream_agent_response
from chatkit.server import ChatKitServer
from chatkit.store import Store
from chatkit.types import (
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
)

from .config import Settings
from .logging_config import bind_logger
from .rag_agent import RAGAgent
from .utils import get_client, wait_for_response_completed

DEFAULT_THREAD_ID = "demo_default_thread"

logger = logging.getLogger(__name__)


class RagChatkitServer(ChatKitServer[dict[str, Any]]):

    def __init__(
            self,
            store: Store,
            settings: Settings
    ) -> None:
        super().__init__(store)
        self.client = get_client(settings)
        self.agent = RAGAgent(settings)

    async def respond(
            self,
            thread: ThreadMetadata,
            input_user_message: Optional[UserMessageItem],
            context,
    ) -> AsyncIterator[ThreadStreamEvent]:
        if input_user_message is None:
            return

        user_message = _user_message_text(input_user_message)
        request_logger = bind_logger(
            logger,
            thread_id=thread.id,
            message_id=input_user_message.id,
        )
        request_logger.info("Invoking agent with %s chars of user input", len(user_message))

        agent_context = AgentContext(
            thread=thread,
            store=self.store,
            request_context={
                'conv_context': context,
                'client': self.client,
            },
        )

        previous_response_id = thread.metadata.get("last_response_id")

        if previous_response_id is not None:
            wait_for_response_completed(
                self.client,
                previous_response_id,
                logger=bind_logger(request_logger, response_id=previous_response_id),
            )

        result = self.agent.invoke(
            user_message,
            agent_context,
            previous_response_id,
        )

        async for event in stream_agent_response(agent_context, result):
            yield event

        response_id = result.raw_responses[-1].response_id
        bind_logger(request_logger, response_id=response_id).info("Persisting last response id")
        thread.metadata["last_response_id"] = response_id
        await self.store.save_thread(thread, context)


def _user_message_text(item: UserMessageItem) -> str:
    parts: list[str] = []
    for part in item.content:
        text = getattr(part, "text", None)
        if text:
            parts.append(text)
    return " ".join(parts).strip()

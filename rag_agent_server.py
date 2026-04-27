import logging
from typing import Any, AsyncIterator

from chatkit.agents import AgentContext, stream_agent_response
from chatkit.server import ChatKitServer
from chatkit.store import Store
from chatkit.types import (
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
)

from config import Settings
from rag_agent import RAGAgent, get_client

DEFAULT_THREAD_ID = "demo_default_thread"


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
            input_user_message: UserMessageItem | None,
            context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        if input_user_message is None:
            return

        user_message = _user_message_text(input_user_message)

        agent_context = AgentContext(
            thread=thread,
            store=self.store,
            request_context={
                'client': self.client,
            },
        )

        previous_response_id = thread.metadata.get("last_response_id")

        result = self.agent.invoke(
            user_message,
            agent_context,
            previous_response_id,
        )

        async for event in stream_agent_response(agent_context, result):
            yield event

        logging.info(f"last response_id = {result.raw_responses[-1].response_id}")
        thread.metadata["last_response_id"] = result.raw_responses[-1].response_id
        await self.store.save_thread(thread, context)


def _user_message_text(item: UserMessageItem) -> str:
    parts: list[str] = []
    for part in item.content:
        text = getattr(part, "text", None)
        if text:
            parts.append(text)
    return " ".join(parts).strip()

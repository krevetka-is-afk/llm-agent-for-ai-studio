import asyncio
import logging
import uuid
from datetime import datetime, timezone

from agents.items import ToolCallItem
from chatkit.types import (
    InferenceOptions,
    ThreadMetadata,
    UserMessageItem,
    UserMessageTextContent,
)

from config import Settings
from memory_store import MemoryStore
from rag_agent_server import DEFAULT_THREAD_ID, RagChatkitServer
from utils import _extract_text

logging.basicConfig(level=logging.INFO, filename='app.log',
                    format='%(asctime)s – %(name)s – %(levelname)s – %(message)s')


async def get_streaming_response(server, thread, item, context={}) -> bool:
    is_done = False
    async for event in server.respond(thread=thread, input_user_message=item, context=context):
        if isinstance(item, ToolCallItem):
            if item.raw_item.name == "finish_dialog":
                is_done = True
        text = _extract_text(event)
        if text:
            print(text, end="", flush=True)
    return is_done


async def chat_loop() -> None:
    print("Welcome to Yandex Cloud Chat!")

    settings = Settings.load_settings()

    exit_chat = False

    store = MemoryStore()

    rag_server = RagChatkitServer(store, settings)
    thread = ThreadMetadata(
        id=DEFAULT_THREAD_ID,
        created_at=datetime.now(timezone.utc),
        metadata={}
    )

    while not exit_chat:
        user_prompt = input("> ")
        if user_prompt == "/exit":
            print("Goodbye!")
            exit_chat = True
            break

        item = UserMessageItem(
            id=str(uuid.uuid4()),
            thread_id=thread.id,
            created_at=datetime.now(timezone.utc),
            content=[UserMessageTextContent(text=user_prompt)],
            inference_options=InferenceOptions()
        )
        print("> Assistant: ", end="", flush=True)
        exit_chat = await get_streaming_response(rag_server, thread, item)
        print(flush=True)


def main():
    asyncio.run(chat_loop())


if __name__ == "__main__":
    main()

import asyncio
import logging
import uuid
from datetime import datetime, timezone
import argparse
from pathlib import Path

from chatkit.types import (
    InferenceOptions,
    ThreadMetadata,
    UserMessageItem,
    UserMessageTextContent,
)

from src.config import Settings
from src.memory_store import MemoryStore
from src.rag_agent_server import DEFAULT_THREAD_ID, RagChatkitServer
from src.utils import _extract_text

logging.basicConfig(level=logging.INFO, filename='app.log',
                    format='%(asctime)s – %(name)s – %(levelname)s – %(message)s')


async def get_streaming_response(server, thread, item, context={}):
    async for event in server.respond(thread=thread, input_user_message=item, context=context):
        text = _extract_text(event)
        if text:
            print(text, end="", flush=True)


class GlobalState:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir).resolve()
        self.is_done = False

    def set_done(self):
        self.is_done = True

    def is_done(self):
        return self.is_done

    def get_base_dir(self):
        return self.base_dir


def parse_args():
    parser = argparse.ArgumentParser(description='My application')
    parser.add_argument('--files-dir', default='files_to_upload', help='Files directory for uploading')
    args = parser.parse_args()
    return args


async def chat_loop() -> None:
    print("Welcome to Yandex Cloud Chat!")

    args = parse_args()
    settings = Settings.load_settings()

    store = MemoryStore()
    gs = GlobalState(args.files_dir)

    rag_server = RagChatkitServer(store, settings)
    thread = ThreadMetadata(
        id=DEFAULT_THREAD_ID,
        created_at=datetime.now(timezone.utc),
        metadata={}
    )

    while not gs.is_done:
        user_prompt = input("> ")
        if user_prompt == "/exit":
            print("Goodbye!")
            gs.set_done()
            break

        item = UserMessageItem(
            id=str(uuid.uuid4()),
            thread_id=thread.id,
            created_at=datetime.now(timezone.utc),
            content=[UserMessageTextContent(text=user_prompt)],
            inference_options=InferenceOptions()
        )
        print("> Assistant: ", end="", flush=True)
        await get_streaming_response(rag_server, thread, item, context=gs)
        print(flush=True)


def main():
    asyncio.run(chat_loop())


if __name__ == "__main__":
    main()

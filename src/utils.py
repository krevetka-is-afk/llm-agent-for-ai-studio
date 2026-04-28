import asyncio
import logging
import time

from openai import OpenAI

from .config import Settings


def get_client(settings: Settings) -> OpenAI:
    return OpenAI(
        api_key=settings.api_key,
        project=settings.folder_id,
        base_url=settings.base_url,
        timeout=settings.timeout,
    )


def wait_for_response_completed(
    client: OpenAI, response_id: str, timeout: float = 30.0, interval: float = 0.5
):
    start = time.time()

    while True:
        if time.time() - start > timeout:
            raise TimeoutError(f"Response {response_id} did not complete within {timeout}s")

        response = client.responses.retrieve(response_id)

        if response.status == "completed":
            logging.info(f"✓ Response {response_id} is completed")
            return response

        elif response.status in ("failed", "cancelled", "incomplete"):
            raise RuntimeError(f"Response ended with unexpected status: {response.status}")

        logging.debug(f"Response {response_id} is {response.status}, waiting...")
        time.sleep(interval)


def extract_text(event) -> str | None:
    """Extract text from ThreadStreamEvent"""
    try:
        if event.type == "thread.item.updated":
            data = event.update

            if hasattr(data, "delta"):
                return data.delta

            if hasattr(data, "text"):
                return data.text
    except Exception as e:
        logging.error(e)
    return None


async def get_streaming_response(server, thread, item, context={}):
    async for event in server.respond(thread=thread, input_user_message=item, context=context):
        if hasattr(event, "type"):
            if event.type == "response.completed":
                logging.info("Response completed successfully")
                break
            elif event.type in ("response.failed", "response.cancelled"):
                logging.warning(f"Response ended with: {event.type}")
                break
        text = extract_text(event)
        if text:
            print(text, end="", flush=True)

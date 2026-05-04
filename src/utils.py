import logging
import time
from typing import Any, Union, Optional

from openai import OpenAI

from .config import Settings
from .logging_config import bind_logger

logger = logging.getLogger(__name__)


def get_client(settings: Settings) -> OpenAI:
    return OpenAI(
        api_key=settings.api_key,
        project=settings.folder_id,
        base_url=settings.base_url,
        timeout=settings.timeout,
    )


def wait_for_response_completed(
        client: OpenAI,
        response_id: str,
        timeout: float = 30.0,
        interval: float = 0.5,
        logger: Union[logging.Logger, logging.LoggerAdapter[Any], None] = None,
):
    base_logger = logger or globals()["logger"]
    wait_logger = bind_logger(base_logger, response_id=response_id)
    start = time.time()

    while True:
        if time.time() - start > timeout:
            raise TimeoutError(f"Response {response_id} did not complete within {timeout}s")

        response = client.responses.retrieve(response_id)

        if response.status == "completed":
            wait_logger.info("Previous response completed")
            return response

        elif response.status in ("failed", "cancelled", "incomplete"):
            raise RuntimeError(f"Response ended with unexpected status: {response.status}")

        wait_logger.debug("Previous response status is %s; waiting", response.status)
        time.sleep(interval)


def extract_text(event) -> Optional[str]:
    """Extract text from ThreadStreamEvent"""
    try:
        if event.type == "thread.item.updated":
            data = event.update

            if hasattr(data, "delta"):
                return data.delta

            if hasattr(data, "text"):
                return data.text
    except Exception as e:
        logger.exception("Failed to extract text from stream event: %s", e)
    return None


async def get_streaming_response(server, thread, item, context=None, logger=None):
    response_context = {} if context is None else context
    base_logger = logger or globals()["logger"]
    response_logger = bind_logger(
        base_logger,
        thread_id=getattr(thread, "id", None),
        message_id=getattr(item, "id", None),
    )
    async for event in server.respond(thread=thread, input_user_message=item, context=response_context):
        if hasattr(event, "type"):
            if event.type == "response.completed":
                response_logger.info("Response completed successfully")
                break
            elif event.type in ("response.failed", "response.cancelled"):
                response_logger.warning("Response ended with %s", event.type)
                break
        text = extract_text(event)
        if text:
            print(text, end="", flush=True)

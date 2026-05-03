import io
import logging

from openai import OpenAI
from openai.types.responses import ResponseTextDeltaEvent

from .config import Settings
from .context import AppContext


def get_user_client(user_api_key: str, user_folder_id: str, settings: Settings) -> OpenAI:
    return OpenAI(
        api_key=user_api_key,
        project=user_folder_id,
        base_url=settings.base_url,
        timeout=settings.timeout,
    )

async def get_streaming_response(server, input_user_message, context: AppContext):
    output = io.StringIO()
    async for event in server.respond(input_user_message=input_user_message, context=context):
        if (
                event.type == "raw_response_event"
                and isinstance(event.data, ResponseTextDeltaEvent)
        ):
            logging.info(f"{event.data.delta=}")
            output.write(event.data.delta)
    return output.getvalue()

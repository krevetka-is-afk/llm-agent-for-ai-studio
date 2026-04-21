import time

from openai import OpenAI
from config import Settings


def get_client(settings: Settings) -> OpenAI:
    return OpenAI(
        api_key=settings.api_key,
        project=settings.folder_id,
        base_url=settings.base_url,
        timeout=settings.timeout,
    )


def ask(client: OpenAI, settings: Settings, prompt: str, is_background=False) -> str:
    response = client.responses.create(
        model=settings.model_uri,
        input=prompt,
        temperature=settings.temperature,
        max_output_tokens=settings.max_output_tokens,
        background=is_background
    )
    if not is_background:
        return response.output_text

    print("please wait", response.id)

    while True:
        status = client.responses.retrieve(response.id)
        print("Статус:", status.status)
        if status.status in ["completed", "failed", "cancelled"]:
            break
        time.sleep(2)

    if status.status == 'completed':
        return status.output_text
    else:
        return status.output_text

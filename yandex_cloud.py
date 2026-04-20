from openai import OpenAI
from config import Settings


def get_client(settings: Settings) -> OpenAI:
    return OpenAI(
        api_key=settings.api_key,
        project=settings.folder_id,
        base_url=settings.base_url,
        timeout=settings.timeout,
    )


def ask(client: OpenAI, settings: Settings, prompt: str) -> str:
    response = client.responses.create(
        model=settings.model_uri,
        input=prompt,
        temperature=settings.temperature,
        max_output_tokens=settings.max_output_tokens,
    )
    return response.output_text

import openai
import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


def main():
    client = get_client()
    answer = ask(client, "Как дела?")
    print(answer)


def get_client() -> openai.OpenAI:
    client = openai.OpenAI(
        api_key=os.getenv("YANDEX_API_KEY"),
        project=os.getenv("YANDEX_FOLDER_ID"),
        base_url="https://ai.api.cloud.yandex.net/v1"
    )
    return client


def ask(client: openai.OpenAI, query: str) -> str:
    response = client.responses.create(
        model=f'gpt://{os.getenv("YANDEX_FOLDER_ID")}/{os.getenv("YANDEX_MODEL")}',
        input=query,
        temperature=0.8,
        max_output_tokens=1500
    )
    return response.output_text


if __name__ == "__main__":
    main()

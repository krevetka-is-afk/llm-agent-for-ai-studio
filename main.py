import openai
import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


def main():
    client = openai.OpenAI(
        api_key=os.getenv("YANDEX_API_KEY"),
        project=os.getenv("YANDEX_FOLDER_ID"),
        base_url="https://ai.api.cloud.yandex.net/v1"
    )
    response = client.responses.create(
        model=f'gpt://{os.getenv("YANDEX_FOLDER_ID")}/{os.getenv("YANDEX_MODEL")}',
        input="Как дела?",
        temperature=0.8,
        max_output_tokens=1500
    )

    print(response.output[0].content[0].text)  # ty: ignore[unresolved-attribute, not-subscriptable]


if __name__ == "__main__":
    main()

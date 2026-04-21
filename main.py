import os
import logging
import pathlib

from langchain_openai import ChatOpenAI
from openai import OpenAI

from run_agent import run_rag_agent

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
BASE_URL = os.getenv("BASE_URL")
MODEL_NAME = os.getenv("MODEL_NAME")


def local_path(path: str) -> pathlib.Path:
    return pathlib.Path(__file__).parent / path


def main():
    logging.basicConfig(filename='test.log', level=logging.INFO)

    TEST_FILES_DIR = local_path("test_files")
    test_files = list(TEST_FILES_DIR.iterdir())

    client = OpenAI(
        api_key=YANDEX_API_KEY,
        base_url=BASE_URL,
        project=YANDEX_FOLDER_ID,
    )

    llm = ChatOpenAI(
        model=f"gpt://{YANDEX_FOLDER_ID}/{MODEL_NAME}",
        temperature=0,
        base_url=BASE_URL,
        api_key=YANDEX_API_KEY,
    )
    response, history, ctx, tracer = run_rag_agent(
        client, llm, "как в документах упоминается мой дядя?", test_files
    )

    print(f"Model response {response}")

    response, history, ctx, tracer = run_rag_agent(
        client,
        llm,
        "какие герои упомянаются в романе?",
        files=test_files,
        history=history,
        ctx=ctx,
        tracer=tracer,
    )

    print(f"Model response {response}")

    tracer.print_trace()

    print(ctx)


if __name__ == "__main__":
    main()

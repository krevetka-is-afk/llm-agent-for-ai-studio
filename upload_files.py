from pathlib import Path
from openai import OpenAI


def local_path(path: str) -> Path:
    return Path(__file__).parent / path


def upload_file(client: OpenAI, path_to_file: str) -> str:
    print(f"Загружаем файл {path_to_file}...")

    f = client.files.create(
        file=open(local_path(path_to_file), "rb"),
        purpose="assistants",
    )
    print(f"Файл {path_to_file} загружен:", f.id)

    return f.id

import time
from pathlib import Path

from openai import OpenAI
from openai.types import (
    FileDeleted,
    FileObject,
    VectorStore,
)
from openai.types.vector_stores import (
    VectorStoreFileDeleted,
)


def upload_file(client: OpenAI, file: bytes) -> FileObject:
    response = client.files.create(
        file=file,
        purpose="assistants",
    )
    return response


def list_files(client: OpenAI) -> list[FileObject]:
    return client.files.list(
        purpose="assistants",
    ).data


def delete_file(client: OpenAI, file_id: str) -> FileDeleted:
    return client.files.delete(file_id)


def build_vector_store_index(
    client: OpenAI, name: str, file_ids: list[str]
) -> VectorStore:
    return client.vector_stores.create(
        name=name,
        metadata={"key": "value"},
        expires_after={"anchor": "last_active_at", "days": 1},
        chunking_strategy={
            "type": "static",
            "static": {
                "max_chunk_size_tokens": 1408,
                "chunk_overlap_tokens": 148,
            },
        },
        file_ids=file_ids,
    )


def wait_vector_store_retrieve(client: OpenAI, vector_store_id: str) -> None:
    while True:
        vector_store = client.vector_stores.retrieve(vector_store_id)
        if vector_store.status == "completed":
            break
        time.sleep(2)


def delete_file_from_index(
    client: OpenAI, file_id: str, vector_store_id: str
) -> VectorStoreFileDeleted:
    return client.vector_stores.files.delete(file_id, vector_store_id=vector_store_id)


def build_vector_store(client: OpenAI, name: str, files: list[Path]) -> str:
    file_objects = []
    for file in files:
        file_obj = upload_file(client, open(file, "rb"))
        file_objects.append(file_obj)

    file_ids = [file_obj.id for file_obj in file_objects]
    vector_store = build_vector_store_index(client, name, file_ids)
    wait_vector_store_retrieve(client, vector_store.id)
    return vector_store.id


def search_vector_store(
    client: OpenAI, vector_store_id: str, query: str, limit: int = 1
) -> list[str]:
    response = client.vector_stores.search(
        vector_store_id,
        query=query,
        max_num_results=limit,
    )

    search_result = [content.content[0].text for content in response.data]
    return search_result

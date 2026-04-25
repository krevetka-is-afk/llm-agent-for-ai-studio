import time
from openai import OpenAI


def create_search_index(client: OpenAI, file_ids: list[str], vector_store_name: str) -> str:
    print("Создаем поисковый индекс...")

    vector_store = client.vector_stores.create(
        name=vector_store_name,
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
    vector_store_id = vector_store.id
    print("Vector Store создан:", vector_store_id)

    while True:
        vector_store = client.vector_stores.retrieve(vector_store_id)
        print("Статус Vector Store:", vector_store.status)
        if vector_store.status == "completed":
            break
        time.sleep(3)

    print("Vector Store готов к работе.")

    return vector_store_id

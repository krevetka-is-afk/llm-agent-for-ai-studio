from openai import OpenAI


def search_in_search_index(client: OpenAI, vector_store_id: str, query: str):
    print(f"Ищем по запросу: {query}")

    results = client.vector_stores.search(vector_store_id, query=query)
    for r in results:
        print("Результат:", r)

    print("Поиск завершен")

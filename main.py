from create_search_index import create_search_index
from config import Settings
from upload_files import upload_file
from yandex_cloud import get_client, ask
from tools import Tools


# from search_in_search_index import search_in_search_index


def main():
    chat_loop()


MENU = '''
to upload file type /upload_file <path_to_file>
to create search index type /create_search_index <vector_store_name>
to search in search index type /search_in_search_index <query>
to exit type /exit
'''


def chat_loop() -> None:
    print("Welcome to Yandex Cloud Chat!")
    print(MENU)

    settings = Settings.load_settings()
    tools = Tools.load_tools()
    client = get_client(settings)
    conv = client.conversations.create()
    uploaded_files_ids = []
    created_vector_store_ids = []

    print("conversation_id:", conv.id)

    exit_chat = False

    while not exit_chat:
        user_prompt = input("> ")
        if user_prompt == "/exit":
            print("Goodbye!")
            exit_chat = True
            break

        elif user_prompt.startswith("/upload_file"):
            path_to_file = user_prompt.strip().split()[1]
            try:
                file_id = upload_file(client=client, path_to_file=path_to_file)
                uploaded_files_ids.append(file_id)
            except Exception as e:
                print("Error uploading file: ", e)

        elif user_prompt.startswith("/create_search_index"):
            vector_store_name = user_prompt.strip().split()[1]
            try:
                vector_store_id = create_search_index(client=client, file_ids=uploaded_files_ids,
                                                      vector_store_name=vector_store_name)
                created_vector_store_ids.append(vector_store_id)
            except Exception as e:
                print("Error creating index: ", e)


        # TODO: редакиторивание стора

        # TODO: перейти на стриминг

        # TODO: завершения диалога

        # Пока без поиска это отдельная функция
        # elif user_prompt.startswith("/search_in_search_index"):
        #     user_query = user_prompt.strip().split()[1]
        #     try:
        #         search_in_search_index(client=client, vector_store_id=vector_store_id[0], query=user_query)
        #     except Exception as e:
        #         print("Error searching index: ", e)

        else:
            answer = ask(
                client,
                settings,
                tools=tools.weather_tool,
                prompt=user_prompt,
                is_background=False,
                conversation_id=conv.id
            )

            print(answer)


if __name__ == "__main__":
    main()

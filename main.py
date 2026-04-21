from config import Settings
from yandex_cloud import get_client, ask


def main():
    settings = Settings.load_settings()
    client = get_client(settings)

    conv = client.conversations.create()
    # print("conversation_id:", conv.id)

    answer = ask(client, settings, prompt="Как дела?", is_background=False, conversation_id=conv.id)
    print(answer)


if __name__ == "__main__":
    main()

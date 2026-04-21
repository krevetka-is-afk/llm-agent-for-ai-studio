from config import Settings
from yandex_cloud import get_client, ask


def main():
    settings = Settings.load_settings()
    client = get_client(settings)
    answer = ask(client, settings, prompt="Как дела?", is_background=True)
    print(answer)


if __name__ == "__main__":
    main()

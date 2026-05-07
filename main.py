import asyncio

from src.app import create_app
from src.config import Settings


async def main() -> None:
    settings = Settings.load_settings()
    bot, dp = create_app(settings)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

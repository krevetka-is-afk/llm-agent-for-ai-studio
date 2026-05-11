import asyncio

from src.app import create_app
from src.config import Settings

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)

async def main() -> None:
    logging.getLogger(__name__).info("Main started")
    settings = Settings.load_settings()
    bot, dp = create_app(settings)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

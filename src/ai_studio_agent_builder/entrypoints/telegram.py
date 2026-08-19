"""Thin executable bootstrap for the experimental Telegram adapter."""

import asyncio
import logging

from ai_studio_agent_builder.composition import (
    build_telegram_runtime,
    configure_telegram_logging,
)


async def main() -> None:
    logging.getLogger(__name__).info("Main started")
    runtime = build_telegram_runtime()
    await runtime.dispatcher.start_polling(runtime.bot)


if __name__ == "__main__":
    configure_telegram_logging()
    asyncio.run(main())

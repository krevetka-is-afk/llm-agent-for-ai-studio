"""Compatibility entrypoint for the packaged Telegram runtime."""

import asyncio

from ai_studio_agent_builder.composition import (
    build_telegram_app as create_app,
    configure_telegram_logging,
)
from ai_studio_agent_builder.entrypoints.telegram import main


if __name__ == "__main__":
    configure_telegram_logging()
    asyncio.run(main())


__all__ = ["create_app", "main"]

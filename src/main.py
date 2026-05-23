import asyncio

from app import create_app
from config import load_config, AppConfig

import logging
import sys
import argparse
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="demo_cli",
        description="Load a YAML configuration file supplied on the command line",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to the YAML configuration file.",
    )

    return parser


async def main(argv: list[str] | None = None) -> None:
    logging.getLogger(__name__).info("Main started")
    args = build_parser().parse_args(argv)
    config: AppConfig = load_config(args.config)
    bot, dp = create_app(config)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

"""Entry point: ``python main.py``."""

from __future__ import annotations

import asyncio
import logging
import sys

from eternal_realm.bot.app import run
from eternal_realm.config import ConfigError, load_settings


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )
    try:
        settings = load_settings("config.toml")
    except ConfigError as error:
        print(f"خطای تنظیمات: {error}", file=sys.stderr)
        return 1
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        logging.getLogger("eternal_realm").info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

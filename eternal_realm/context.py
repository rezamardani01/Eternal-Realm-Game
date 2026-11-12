"""Shared dependencies handed to every service."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .config import Balance, Settings
from .db.database import Database


def utc_now() -> int:
    return int(time.time())


@dataclass
class AppContext:
    db: Database
    settings: Settings
    clock: Callable[[], int] = utc_now
    rng: random.Random = field(default_factory=random.Random)

    @property
    def balance(self) -> Balance:
        return self.settings.balance

    async def pause(self, factor: float = 1.0) -> None:
        """Wait a beat between animation frames."""
        delay = self.balance.animation_seconds * factor
        if delay > 0:
            await asyncio.sleep(delay)

    async def wait(self, seconds: float) -> None:
        """A real wait (a group dungeon in progress), unlike :meth:`pause`, which only spaces animation frames."""
        if seconds > 0:
            await asyncio.sleep(seconds)

    def now(self) -> int:
        return self.clock()

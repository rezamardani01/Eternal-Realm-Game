"""Shared dependencies handed to every service."""

from __future__ import annotations

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

    def now(self) -> int:
        return self.clock()

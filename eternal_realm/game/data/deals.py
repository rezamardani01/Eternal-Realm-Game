"""Today's discounts: a few products from the shop sold cheaper until Tehran midnight.

The selection is derived from the day number, so it needs no storage and is the same for everyone.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .packs import PACKS, Pack

DISCOUNTS = (20, 25, 30, 40, 50)
DEALS_PER_DAY = 5
TEHRAN_OFFSET = 12600  # UTC+3:30


@dataclass(frozen=True)
class Deal:
    pack: Pack
    percent: int
    price_rial: int

    @property
    def price_toman(self) -> int:
        return self.price_rial // 10


def day_number(now: int) -> int:
    return (now + TEHRAN_OFFSET) // 86400


def seconds_left(now: int) -> int:
    return 86400 - (now + TEHRAN_OFFSET) % 86400


def discounted(price_rial: int, percent: int) -> int:
    """The sale price, rounded to a tidy 1,000 rial and never below 10,000."""
    return max(10_000, round(price_rial * (100 - percent) / 100 / 1000) * 1000)


def daily_deals(now: int) -> list[Deal]:
    rng = random.Random(f"deals-{day_number(now)}")
    candidates = [p for p in PACKS.values() if not p.lucky]
    chosen = rng.sample(candidates, DEALS_PER_DAY)
    return [Deal(p, pct := rng.choice(DISCOUNTS), discounted(p.price_rial, pct)) for p in chosen]


def find_deal(now: int, pack_id: str) -> Deal | None:
    return next((d for d in daily_deals(now) if d.pack.id == pack_id), None)

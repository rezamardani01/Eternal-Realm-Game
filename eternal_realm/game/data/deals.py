"""Today's discounts: a few products from the shop sold cheaper until Tehran midnight.

The selection is derived from the day number, so it needs no storage and is the same for everyone.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from .packs import PACKS, Pack

DISCOUNTS = (20, 25, 30, 40, 50)
TEHRAN_OFFSET = 12600  # UTC+3:30

#: what a day's deals are made of: one of each, so the list is varied and always has the valuable things on sale
#: (a coin pack, an experience pack, crystals, a rare material, a legendary kit or piece of gear, and one other product)
SLOTS: tuple[tuple[str, Callable[[Pack], bool]], ...] = (
    ("coins", lambda p: p.section == "coins"),
    ("xp", lambda p: p.section == "xp"),
    ("crystals", lambda p: p.section == "crystals"),
    ("rare", lambda p: p.section == "rare" and not p.id.startswith("kit_")),
    ("legendary", lambda p: p.id.startswith("kit_") or p.section == "deal"),
    ("other", lambda p: True),
)
DEALS_PER_DAY = len(SLOTS)


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


def kinds(pack: Pack) -> frozenset[str]:
    """What a pack gives, as names: the items, the currencies, the pet... Two deals of one day never share one."""
    names = set(pack.items)
    for field, name in (("gold", "gold"), ("crystal", "crystal"), ("xp", "xp"), ("boost_hours", "boost"), ("spins", "wheel"), ("vip_days", "vip"), ("season", "season")):
        if getattr(pack, field):
            names.add(name)
    if pack.pet:
        names.add(f"pet:{pack.pet}")
    if pack.city:
        names.add("city:" + "+".join(sorted(pack.city)))
    if pack.city_shield_hours:
        names.add("city_shield")
    return frozenset(names)


def daily_deals(now: int) -> list[Deal]:
    rng = random.Random(f"deals-{day_number(now)}")
    candidates = [p for p in PACKS.values() if not p.lucky]
    chosen: list[Pack] = []
    taken: set[str] = set()
    for _, wanted in SLOTS:
        pool = [p for p in candidates if wanted(p) and p not in chosen and not kinds(p) & taken]
        if pool:
            pick = rng.choice(pool)
            chosen.append(pick)
            taken |= kinds(pick)
    return [Deal(p, pct := rng.choice(DISCOUNTS), discounted(p.price_rial, pct)) for p in chosen]


def find_deal(now: int, pack_id: str) -> Deal | None:
    return next((d for d in daily_deals(now) if d.pack.id == pack_id), None)

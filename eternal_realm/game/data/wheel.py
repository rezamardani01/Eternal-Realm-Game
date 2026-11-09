"""The wheel of fortune (گردونه شانس): spins are bought with real money, prizes are public.

Most slices are valuable; a few are empty. Change weights freely, the odds screen reads this table.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .items import get_item


@dataclass(frozen=True)
class Slice:
    id: str
    emoji: str
    label: str
    weight: float
    gold: int = 0
    crystal: int = 0
    items: tuple[tuple[str, int], ...] = ()
    #: shown with extra fanfare
    jackpot: bool = False

    @property
    def empty(self) -> bool:
        return not (self.gold or self.crystal or self.items)


SLICES: tuple[Slice, ...] = (
    Slice("empty", "💨", "پوچ", 12),
    Slice("gold_s", "🪙", "۱۵٬۰۰۰ سکه", 17, gold=15_000),
    Slice("gold_m", "💰", "۴۰٬۰۰۰ سکه", 8, gold=40_000),
    Slice("gold_l", "🏦", "۱۵۰٬۰۰۰ سکه", 1.5, gold=150_000, jackpot=True),
    Slice("crystal_s", "💎", "۱۵ کریستال", 12, crystal=15),
    Slice("crystal_m", "💎", "۴۰ کریستال", 5, crystal=40),
    Slice("crystal_l", "💠", "۱۵۰ کریستال", 1.5, crystal=150, jackpot=True),
    Slice("magic_chest", "🎁", "صندوقچه جادویی", 12, items=(("magic_chest", 1),)),
    Slice("royal_chest", "👑", "صندوقچه سلطنتی", 5, items=(("royal_chest", 1),)),
    Slice("scales", "🐉", "۲ فلس اژدها", 7, items=(("dragon_scale", 2),)),
    Slice("shards", "💠", "۵ پاره‌کریستال", 7, items=(("crystal_shard", 5),)),
    Slice("energy", "🍶", "۳ معجون انرژی بی‌کران", 5, items=(("grand_energy_potion", 3),)),
    Slice("dagger", "🗡️", "خنجر سایه", 3, items=(("shadow_dagger", 1),)),
    Slice("sword", "🔥", "شمشیر آتشین", 2, items=(("fire_sword", 1),), jackpot=True),
    Slice("armor", "🐲", "زره اژدها", 1.5, items=(("dragon_armor", 1),), jackpot=True),
    Slice("class", "🎫", "برگه‌ی تغییر کلاس", 1, items=(("class_ticket", 1),)),
)
_BY_ID = {s.id: s for s in SLICES}

#: spins per pack are in packs.py; this is the size of the strip shown while the wheel turns
STRIP = 5


def get_slice(slice_id: str) -> Slice:
    return _BY_ID[slice_id]


def odds() -> list[tuple[Slice, float]]:
    total = sum(s.weight for s in SLICES)
    return [(s, s.weight / total) for s in SLICES]


def spin(rng: random.Random) -> Slice:
    return rng.choices(SLICES, weights=[s.weight for s in SLICES], k=1)[0]


def describe(s: Slice) -> str:
    """A plain label for the prize (items by name)."""
    if s.items and not s.gold and not s.crystal:
        item_id, qty = s.items[0]
        return get_item(item_id).name + (f" ×{qty}" if qty > 1 else "")
    return s.label

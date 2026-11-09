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
    # small consolation prizes: every spin pays something
    Slice("ore", "⛓️", "۸ سنگ آهن", 6, items=(("iron_ore", 8),)),
    Slice("potion", "⚡", "۳ معجون انرژی", 6, items=(("energy_potion", 3),)),
    Slice("herb", "🌿", "۱۰ گیاه شفابخش", 3, items=(("herb", 10),)),
    # money
    Slice("gold_s", "🪙", "۲۰٬۰۰۰ سکه", 12, gold=20_000),
    Slice("gold_m", "💰", "۶۰٬۰۰۰ سکه", 8, gold=60_000),
    Slice("gold_l", "🏦", "۲۵۰٬۰۰۰ سکه", 1.5, gold=250_000, jackpot=True),
    Slice("crystal_s", "💎", "۱۵ کریستال", 9, crystal=15),
    Slice("crystal_m", "💎", "۴۰ کریستال", 5, crystal=40),
    Slice("crystal_l", "💠", "۱۵۰ کریستال", 1.5, crystal=150, jackpot=True),
    # treasure for those who are already strong
    Slice("magic_chest", "🎁", "صندوقچه جادویی", 9, items=(("magic_chest", 1),)),
    Slice("royal_chest", "👑", "صندوقچه سلطنتی", 6, items=(("royal_chest", 1),)),
    Slice("scales", "🐉", "۳ فلس اژدها", 6, items=(("dragon_scale", 3),)),
    Slice("shards", "💠", "۸ پاره‌کریستال", 6, items=(("crystal_shard", 8),)),
    Slice("energy", "🍶", "۵ معجون انرژی بی‌کران", 4, items=(("grand_energy_potion", 5),)),
    Slice("knight_sword", "⚔️", "شمشیر شوالیه", 3, items=(("knight_sword", 1),)),
    Slice("knight_armor", "🦺", "زره شوالیه", 3, items=(("knight_armor", 1),)),
    Slice("war_hammer", "🔨", "پتک جنگ", 2.5, items=(("war_hammer", 1),)),
    Slice("storm_staff", "⚡", "عصای طوفان", 2.5, items=(("storm_staff", 1),)),
    Slice("elven_bow", "🏹", "کمان الفی", 2.5, items=(("elven_bow", 1),)),
    Slice("assassin_blade", "🗡️", "تیغ آدم‌کش", 2.5, items=(("assassin_blade", 1),)),
    Slice("knight_shield", "🛡️", "سپر شوالیه", 2, items=(("knight_shield", 1),)),
    Slice("knight_helm", "🪖", "کلاه‌خود شوالیه", 2, items=(("knight_helm", 1),)),
    Slice("wind_boots", "👟", "چکمه باد", 2, items=(("wind_boots", 1),)),
    Slice("ward_amulet", "📿", "گردنبند نگهبان", 2, items=(("ward_amulet", 1),)),
    Slice("dagger", "🌑", "خنجر سایه", 3, items=(("shadow_dagger", 1),)),
    Slice("helm", "🪖", "کلاه‌خود اژدهاکش", 1.5, items=(("dragonbane_helm", 1),), jackpot=True),
    Slice("boots", "👢", "چکمه اژدهاکش", 1.5, items=(("dragonbane_boots", 1),), jackpot=True),
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

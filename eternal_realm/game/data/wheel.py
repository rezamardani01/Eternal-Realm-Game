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
    Slice("shard_2", "💠", "۲ پاره‌کریستال", 3, items=(("crystal_shard", 2),)),
    Slice("ore_20", "⛓️", "۲۰ سنگ آهن", 3, items=(("iron_ore", 20),)),
    Slice("goldore_5", "🥇", "۵ سنگ طلا", 2.5, items=(("gold_ore", 5),)),
    Slice("moon_5", "🍀", "۵ گیاه ماه‌تاب", 2.5, items=(("moon_herb", 5),)),
    Slice("scroll_5", "📜", "۵ طومار کهنه", 2.5, items=(("old_scroll", 5),)),
    Slice("fang_10", "🦷", "۱۰ دندان هیولا", 2.5, items=(("monster_fang", 10),)),
    Slice("potion_10", "🔋", "۱۰ معجون انرژی بزرگ", 2, items=(("big_energy_potion", 10),)),
    Slice("honey_5", "🍯", "۵ عسل طلایی", 2, items=(("honey", 5),)),
    Slice("coin_3", "🏺", "۳ سکه‌ی باستانی", 2, items=(("ancient_coin", 3),)),
    Slice("hide_10", "🧶", "۱۰ پوست هیولا", 2, items=(("monster_hide", 10),)),
    Slice("shard_4", "💠", "۴ پاره‌کریستال", 3, items=(("crystal_shard", 4),)),
    Slice("scale_3", "🐉", "۳ فلس اژدها", 1.5, items=(("dragon_scale", 3),), jackpot=True),
    Slice("shard_8", "💠", "۸ پاره‌کریستال", 1.5, items=(("crystal_shard", 8),), jackpot=True),
    Slice("scale_2", "🐉", "۲ فلس اژدها", 2, items=(("dragon_scale", 2),), jackpot=True),
    Slice("scale_5", "🐲", "۵ فلس اژدها", 1.5, items=(("dragon_scale", 5),), jackpot=True),
    Slice("class", "🎫", "برگه‌ی تغییر کلاس", 1, items=(("class_ticket", 1),)),
)
#: the prizes of the daily free spin: friendly, never empty, sometimes lovely
FREE_SLICES: tuple[Slice, ...] = (
    Slice("f_gold_s", "🪙", "۳٬۰۰۰ سکه", 20, gold=3_000),
    Slice("f_gold_m", "💰", "۸٬۰۰۰ سکه", 12, gold=8_000),
    Slice("f_crystal_s", "💎", "۲ کریستال", 14, crystal=2),
    Slice("f_crystal_m", "💎", "۵ کریستال", 6, crystal=5),
    Slice("f_crystal_l", "💠", "۱۰ کریستال", 2, crystal=10, jackpot=True),
    Slice("f_wooden", "📦", "صندوقچه چوبی", 12, items=(("wooden_chest", 1),)),
    Slice("f_potion", "⚡", "۲ معجون انرژی", 10, items=(("energy_potion", 2),)),
    Slice("f_ore", "⛓️", "۶ سنگ آهن", 8, items=(("iron_ore", 6),)),
    Slice("f_herb", "🌿", "۸ گیاه شفابخش", 6, items=(("herb", 8),)),
    Slice("f_big", "🔋", "معجون انرژی بزرگ", 6, items=(("big_energy_potion", 1),)),
    Slice("f_magic", "🎁", "صندوقچه جادویی", 4, items=(("magic_chest", 1),), jackpot=True),
)
_BY_ID = {s.id: s for s in (*SLICES, *FREE_SLICES)}

#: spins per pack are in packs.py; this is the size of the strip shown while the wheel turns
STRIP = 5


def get_slice(slice_id: str) -> Slice:
    return _BY_ID[slice_id]


def odds() -> list[tuple[Slice, float]]:
    total = sum(s.weight for s in SLICES)
    return [(s, s.weight / total) for s in SLICES]


def spin(rng: random.Random, free: bool = False) -> Slice:
    table = FREE_SLICES if free else SLICES
    return rng.choices(table, weights=[s.weight for s in table], k=1)[0]


def describe(s: Slice) -> str:
    """A plain label for the prize (items by name)."""
    if s.items and not s.gold and not s.crystal:
        item_id, qty = s.items[0]
        return get_item(item_id).name + (f" ×{qty}" if qty > 1 else "")
    return s.label

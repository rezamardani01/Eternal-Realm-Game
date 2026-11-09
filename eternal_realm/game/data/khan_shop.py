"""The clan shop: a few valuable goods each day, paid for in Khan points (earned in clan-versus-clan duels)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .items import get_item

PER_DAY = 6
#: Khan points for a duel won / lost against a member of another clan
DUEL_WIN_POINTS = 3
DUEL_LOSE_POINTS = 1
#: Khan points for the top three clans of the weekly war
WAR_POINTS = (30, 20, 10)


@dataclass(frozen=True)
class Offer:
    id: str
    #: ``item``, ``crystal`` or ``gold``
    kind: str
    ref: str
    qty: int
    price: int

    @property
    def title(self) -> str:
        if self.kind == "item":
            item = get_item(self.ref)
            return f"{item.emoji} {item.name} ×{self.qty}" if self.qty > 1 else f"{item.emoji} {item.name}"
        if self.kind == "crystal":
            return f"💎 {self.qty} کریستال"
        return f"🪙 {self.qty} سکه"


POOL: tuple[Offer, ...] = (
    Offer("wooden_chest", "item", "wooden_chest", 3, 30),
    Offer("magic_chest", "item", "magic_chest", 1, 45),
    Offer("royal_chest", "item", "royal_chest", 1, 130),
    Offer("shard", "item", "crystal_shard", 3, 60),
    Offer("scale", "item", "dragon_scale", 1, 90),
    Offer("big_energy", "item", "big_energy_potion", 3, 30),
    Offer("grand_energy", "item", "grand_energy_potion", 1, 45),
    Offer("gold_ore", "item", "gold_ore", 5, 25),
    Offer("moon_herb", "item", "moon_herb", 5, 20),
    Offer("iron_ore", "item", "iron_ore", 10, 15),
    Offer("golden_fish", "item", "golden_fish", 3, 25),
    Offer("rename", "item", "rename_ticket", 1, 150),
    Offer("class_ticket", "item", "class_ticket", 1, 400),
    Offer("race_ticket", "item", "race_ticket", 1, 400),
    Offer("crystals", "crystal", "", 20, 80),
    Offer("coins", "gold", "", 5_000, 40),
)
_BY_ID = {o.id: o for o in POOL}


def get_offer(offer_id: str) -> Offer:
    return _BY_ID[offer_id]


def day_of(now: int) -> int:
    return (now + 12600) // 86400


def offers_for(day: int) -> list[Offer]:
    """Today's goods: the same for everybody, a different pick every day."""
    return random.Random(day * 7919 + 13).sample(POOL, PER_DAY)

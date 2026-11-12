"""Daily lucky bundles: a guaranteed amount of gold plus a few random prizes from today's theme.

The theme changes every day (UTC day number), the odds are public in the shop.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .chests import Prize


@dataclass(frozen=True)
class Theme:
    id: str
    emoji: str
    name: str
    prizes: tuple[Prize, ...]


@dataclass(frozen=True)
class Tier:
    rolls: int
    guaranteed_gold: int


THEMES: tuple[Theme, ...] = (
    Theme("forge", "⚒️", "آهنگری", (
        Prize(30, item_id="iron_ore", qty=(5, 12)),
        Prize(16, item_id="gold_ore", qty=(1, 3)),
        Prize(14, item_id="crystal_shard", qty=(1, 2)),
        Prize(8, item_id="iron_ore"),
        Prize(6, item_id="iron_ore"),
        Prize(4, item_id="gold_ore"),
        Prize(3, item_id="gold_ore"),
        Prize(2, item_id="moon_herb"),
        Prize(1, crystal=(1, 2)),
    )),
    Theme("wild", "🌲", "سرزمین وحشی", (
        Prize(25, item_id="herb", qty=(3, 6)),
        Prize(18, item_id="moon_herb", qty=(1, 3)),
        Prize(15, item_id="monster_fang", qty=(1, 3)),
        Prize(15, item_id="monster_hide", qty=(2, 5)),
        Prize(14, item_id="energy_potion", qty=(1, 2)),
        Prize(6, item_id="big_energy_potion"),
        Prize(4, item_id="wooden_chest"),
        Prize(3, item_id="dragon_scale"),
        Prize(2, crystal=(1, 1)),
    )),
    Theme("fortune", "🍀", "بخت و اقبال", (
        Prize(28, gold=(300, 1200)),
        Prize(16, item_id="crystal_shard", qty=(1, 3)),
        Prize(16, item_id="wooden_chest"),
        Prize(14, crystal=(1, 4)),
        Prize(12, item_id="big_energy_potion"),
        Prize(6, item_id="magic_chest"),
        Prize(8, item_id="moon_herb"),
    )),
)

TIERS: dict[str, Tier] = {
    "lucky_s": Tier(rolls=3, guaranteed_gold=1_500),
    "lucky_m": Tier(rolls=5, guaranteed_gold=6_000),
    "lucky_l": Tier(rolls=8, guaranteed_gold=20_000),
}


@dataclass
class Haul:
    gold: int = 0
    crystal: int = 0
    items: dict[str, int] = field(default_factory=dict)


def theme_of_day(timestamp: int) -> Theme:
    return THEMES[(timestamp // 86400) % len(THEMES)]


def odds(theme: Theme) -> list[tuple[Prize, float]]:
    total = sum(p.weight for p in theme.prizes)
    return [(p, p.weight / total) for p in theme.prizes]


def roll(pack_id: str, theme: Theme, rng: random.Random) -> Haul:
    tier = TIERS[pack_id]
    haul = Haul(gold=tier.guaranteed_gold)
    for prize in rng.choices(theme.prizes, weights=[p.weight for p in theme.prizes], k=tier.rolls):
        if prize.gold[1]:
            haul.gold += rng.randint(*prize.gold)
        if prize.crystal[1]:
            haul.crystal += rng.randint(*prize.crystal)
        if prize.item_id:
            haul.items[prize.item_id] = haul.items.get(prize.item_id, 0) + rng.randint(*prize.qty)
    return haul

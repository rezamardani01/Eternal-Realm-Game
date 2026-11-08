"""Equipment sets: wearing several pieces of one set unlocks extra bonuses."""

from __future__ import annotations

from dataclasses import dataclass

from .stats import Stats


@dataclass(frozen=True)
class GearSet:
    id: str
    emoji: str
    name: str
    pieces: tuple[str, ...]
    #: number of worn pieces -> extra stats (every threshold already reached applies)
    bonuses: tuple[tuple[int, Stats], ...]


SETS: tuple[GearSet, ...] = (
    GearSet(
        "iron", "⚙️", "ست آهنین", ("iron_sword", "iron_shield", "iron_helm"),
        ((2, Stats(defense=3)), (3, Stats(atk=5, hp=25))),
    ),
    GearSet(
        "leather", "🍂", "ست چرمی", ("leather_cap", "leather_armor", "leather_boots"),
        ((2, Stats(speed=3)), (3, Stats(hp=30, luck=3))),
    ),
    GearSet(
        "dragonbane", "🐲", "ست اژدهاکُش", ("fire_sword", "dragon_armor", "dragonbane_helm", "dragonbane_boots"),
        ((2, Stats(atk=6, magic=4)), (4, Stats(hp=90, defense=12, atk=10))),
    ),
)

_BY_ITEM = {piece: s for s in SETS for piece in s.pieces}


def set_of(item_id: str) -> GearSet | None:
    return _BY_ITEM.get(item_id)


def set_bonus(worn_item_ids: list[str]) -> Stats:
    """Total extra stats from every set the player is partly or fully wearing."""
    total = Stats()
    for gear_set in SETS:
        count = sum(1 for i in worn_item_ids if i in gear_set.pieces)
        for need, stats in gear_set.bonuses:
            if count >= need:
                total = total + stats
    return total


def worn_count(gear_set: GearSet, worn_item_ids: list[str]) -> int:
    return sum(1 for i in worn_item_ids if i in gear_set.pieces)


#: gear that bosses may drop as a trophy, with the weight of each
BOSS_DROPS: tuple[tuple[str, int], ...] = (
    ("dragonbane_helm", 20), ("dragonbane_boots", 20), ("fire_sword", 8), ("dragon_armor", 8),
    ("shadow_dagger", 10), ("crystal_staff", 14), ("steel_sword", 20), ("hunter_bow", 20),
)


#: uses of a weapon -> bond level; each level adds 5% of the weapon's own stats
BOND_STEPS = (25, 75, 150)
BOND_NAMES = ("غریبه", "آشنا", "یار", "هم‌خون")


def bond_level(uses: int) -> int:
    return sum(1 for need in BOND_STEPS if uses >= need)

"""Chest loot tables. Odds are computed from the weights and shown to players before they buy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prize:
    weight: float
    gold: tuple[int, int] = (0, 0)
    crystal: tuple[int, int] = (0, 0)
    item_id: str | None = None
    qty: tuple[int, int] = (1, 1)


@dataclass(frozen=True)
class Chest:
    item_id: str
    #: ("gold" | "crystal", amount) when the chest can be bought with in-game currency
    price: tuple[str, int] | None
    prizes: tuple[Prize, ...]

    @property
    def total_weight(self) -> float:
        return sum(p.weight for p in self.prizes)


CHESTS: dict[str, Chest] = {
    c.item_id: c
    for c in (
        Chest(
            "wooden_chest", ("gold", 600),
            (
                Prize(34, gold=(80, 260)),
                Prize(24, item_id="iron_ore", qty=(2, 5)),
                Prize(16, item_id="energy_potion", qty=(1, 2)),
                Prize(12, item_id="herb", qty=(3, 6)),
                Prize(8, item_id="leather_armor"),
                Prize(4, item_id="trout", qty=(2, 4)),
                Prize(1.5, item_id="crystal_shard"),
                Prize(0.5, crystal=(1, 1)),
            ),
        ),
        Chest(
            "magic_chest", ("crystal", 30),
            (
                Prize(28, gold=(400, 1200)),
                Prize(20, item_id="crystal_shard", qty=(1, 3)),
                Prize(14, item_id="big_energy_potion"),
                Prize(10, item_id="gold_ore", qty=(2, 4)),
                Prize(6, crystal=(4, 9)),
                Prize(4, item_id="steel_sword"),
                Prize(4, item_id="hunter_bow"),
                Prize(4, item_id="chain_mail"),
                Prize(3, item_id="swift_boots"),
                Prize(2.5, item_id="strength_ring"),
                Prize(2.5, item_id="luck_ring"),
                Prize(2, item_id="life_amulet"),
            ),
        ),
        Chest(
            "royal_chest", ("crystal", 120),
            (
                Prize(26, gold=(2000, 5000)),
                Prize(18, crystal=(10, 25)),
                Prize(16, item_id="big_energy_potion", qty=(2, 4)),
                Prize(12, item_id="dragon_scale"),
                Prize(10, item_id="crystal_shard", qty=(3, 6)),
                Prize(6, item_id="crystal_staff"),
                Prize(5, item_id="shadow_dagger"),
                Prize(4, item_id="fire_sword"),
                Prize(3, item_id="dragon_armor"),
            ),
        ),
    )
}

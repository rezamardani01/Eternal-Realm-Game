"""Forge recipes: combine a base piece of gear with materials and gold into a stronger one."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Recipe:
    id: str
    result: str
    #: a gear piece that is used up (must not be worn or listed); "" for none
    base: str = ""
    materials: dict[str, int] = field(default_factory=dict)
    gold: int = 0


RECIPES: tuple[Recipe, ...] = (
    Recipe("fire_sword", "fire_sword", "steel_sword", {"dragon_scale": 3, "crystal_shard": 5, "iron_ore": 10}, 2500),
    Recipe("dragon_armor", "dragon_armor", "chain_mail", {"dragon_scale": 5, "crystal_shard": 4, "iron_ore": 12}, 3500),
    Recipe("shadow_dagger", "shadow_dagger", "dagger", {"crystal_shard": 3, "gold_ore": 4, "monster_fang": 6}, 1800),
    Recipe("crystal_staff", "crystal_staff", "wooden_staff", {"crystal_shard": 6, "moon_herb": 4, "old_scroll": 3}, 2200),
    Recipe("dragonbane_helm", "dragonbane_helm", "iron_helm", {"dragon_scale": 3, "iron_ore": 8}, 2000),
    Recipe("dragonbane_boots", "dragonbane_boots", "swift_boots", {"dragon_scale": 3, "monster_hide": 8}, 2000),
)

_BY_ID = {r.id: r for r in RECIPES}


def get_recipe(recipe_id: str) -> Recipe:
    return _BY_ID[recipe_id]

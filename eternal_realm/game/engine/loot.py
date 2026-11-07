"""Rolling the result of an activity (pure, deterministic for a given ``random.Random``)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..data.activities import Activity, Outcome


@dataclass
class Rolled:
    outcome: Outcome
    gold: int = 0
    xp: int = 0
    crystal: int = 0
    items: dict[str, int] = field(default_factory=dict)


def level_scale(level: int) -> float:
    return 1 + (level - 1) * 0.05


def xp_scale(level: int) -> float:
    return 1 + (level - 1) * 0.12


def pick_outcome(activity: Activity, level: int, luck: int, rng: random.Random) -> Outcome:
    pool = [o for o in activity.outcomes if o.min_level <= level]
    weights = [o.weight * (1 + luck * 0.01) if o.rare else o.weight for o in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def roll(
    activity: Activity, level: int, luck: int, perk: float, rng: random.Random
) -> Rolled:
    """Pick an outcome and turn it into concrete rewards.

    ``perk`` is the race multiplier for this activity (1.0 = none): it boosts gold and
    the quantity of dropped items.
    """
    outcome = pick_outcome(activity, level, luck, rng)
    rolled = Rolled(outcome)
    if outcome.gold[1] > 0:
        rolled.gold = round(rng.randint(*outcome.gold) * level_scale(level) * perk)
    if outcome.xp[1] > 0:
        rolled.xp = round(rng.randint(*outcome.xp) * xp_scale(level))
    rolled.crystal = outcome.crystal
    for drop in outcome.drops:
        if rng.random() > drop.chance:
            continue
        qty = rng.randint(*drop.qty)
        if perk > 1:  # fractional part becomes a chance of one extra item
            scaled = qty * perk
            qty = int(scaled) + (1 if rng.random() < scaled - int(scaled) else 0)
        if qty > 0:
            rolled.items[drop.item_id] = rolled.items.get(drop.item_id, 0) + qty
    return rolled

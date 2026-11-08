"""Levels, experience, energy and derived character stats (pure functions)."""

from __future__ import annotations

from ...config import Balance
from ..data.classes import CLASSES
from ..data.races import RACES
from ..data.stats import BASE_STATS, Stats


def xp_needed(level: int, balance: Balance) -> int:
    """Experience required to go from ``level`` to ``level + 1``."""
    return round(balance.xp_base * level**balance.xp_exponent)


def max_energy(level: int, balance: Balance) -> int:
    return balance.base_energy + balance.energy_per_level * (level - 1)


def apply_xp(level: int, xp: int, gained: int, balance: Balance) -> tuple[int, int, int]:
    """Add ``gained`` experience. Returns ``(new_level, new_xp, levels_gained)``."""
    xp += max(0, gained)
    start = level
    while level < balance.max_level and xp >= xp_needed(level, balance):
        xp -= xp_needed(level, balance)
        level += 1
    if level >= balance.max_level:
        xp = 0
    return level, xp, level - start


def regen_energy(
    stored: int, stored_at: int, now: int, level: int, balance: Balance
) -> tuple[int, int]:
    """Lazy energy regeneration. Returns ``(energy_now, new_energy_at)``."""
    cap = max_energy(level, balance)
    if stored >= cap:
        return stored, now
    gained = max(0, now - stored_at) // balance.energy_regen_seconds
    energy = min(cap, stored + gained)
    if energy >= cap:
        return energy, now
    return energy, stored_at + gained * balance.energy_regen_seconds


def seconds_to_next_energy(stored_at: int, now: int, balance: Balance) -> int:
    return max(0, balance.energy_regen_seconds - (now - stored_at) % balance.energy_regen_seconds)


SECOND_CLASS_SHARE = 0.5
AWAKENING_SHARE = 0.10


def base_stats(race_id: str, class_id: str, level: int, class2_id: str = "", awakened: bool = False) -> Stats:
    """Stats from race, class and level, before any equipment.

    A second class adds half of its starting stats and growth; the awakening doubles the race bonus
    and adds a tenth on top of everything.
    """
    race, cls = RACES[race_id], CLASSES[class_id]
    total = BASE_STATS + race.stats + cls.stats
    grown = [round(g * (level - 1)) for g in cls.growth]
    total = total + Stats(*grown)
    if class2_id:
        other = CLASSES[class2_id]
        extra = other.stats + Stats(*[round(g * (level - 1)) for g in other.growth])
        total = total + extra.scaled(SECOND_CLASS_SHARE)
    if awakened:
        total = total + race.stats
        total = total + total.scaled(AWAKENING_SHARE)
    return total

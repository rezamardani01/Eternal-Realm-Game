"""Daily missions, picked for each player from what suits their level and situation."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from .offers import Facts

PER_DAY = 3


@dataclass(frozen=True)
class MissionKind:
    id: str
    #: the deed that advances it (see ``season.POINTS`` for the names)
    deed: str
    emoji: str
    title: str
    target: int
    fits: Callable[[Facts], bool]
    #: weight when picking (higher = more likely)
    weight: int = 10


KINDS: tuple[MissionKind, ...] = (
    MissionKind("act5", "activity", "🎣", "پنج بار ماهیگیری، معدن، گیاه یا جستجو برو", 5, lambda f: True),
    MissionKind("hunt3", "hunt", "🏹", "سه هیولا را شکار کن", 3, lambda f: True),
    MissionKind("daily", "daily", "🎁", "جایزه‌ی روزانه‌ات را بردار", 1, lambda f: True, 4),
    MissionKind("duel1", "duel_win", "⚔️", "در یک دوئل پیروز شو", 1, lambda f: f.level >= 3),
    MissionKind("boss1", "boss", "🐉", "در یک نبرد باس شرکت کن", 1, lambda f: f.level >= 3),
    MissionKind("quest1", "quest", "📜", "یک داستان را به پایان برسان", 1, lambda f: f.level >= 3, 6),
    MissionKind("dungeon1", "dungeon", "🕳️", "به سیاه‌چال برو", 1, lambda f: f.level >= 8),
    MissionKind("pack1", "card_pack", "🃏", "یک بسته‌ی کارت باز کن", 1, lambda f: f.gold >= 1500, 6),
    MissionKind("clan2", "duel_win", "🏯", "برای خاندانت دو دوئل ببر", 2, lambda f: f.in_clan and f.level >= 3, 12),
    MissionKind("hunt6", "hunt", "🏹", "شش هیولا را شکار کن", 6, lambda f: f.level >= 10, 8),
    MissionKind("recover", "activity", "🌿", "سه کار آرام بکن تا نیرو بگیری", 3, lambda f: f.losses > f.wins and f.losses >= 3, 14),
)

_BY_ID = {k.id: k for k in KINDS}


def get_kind(kind_id: str) -> MissionKind:
    return _BY_ID[kind_id]


def pick(facts: Facts, player_id: int, day: int, count: int = PER_DAY) -> list[MissionKind]:
    """Deterministic for a player and a day: reopening the screen never reshuffles the missions."""
    rng = random.Random(player_id * 100_003 + day)
    pool = [k for k in KINDS if k.fits(facts)]
    chosen: list[MissionKind] = []
    while pool and len(chosen) < count:
        pick_ = rng.choices(pool, weights=[k.weight for k in pool], k=1)[0]
        chosen.append(pick_)
        pool = [k for k in pool if k.id != pick_.id and k.deed != pick_.deed]  # one mission per kind of deed
    return chosen


def reward_for(kind: MissionKind, level: int) -> int:
    return round((60 + 12 * level) * (1 + 0.15 * (kind.target - 1)))

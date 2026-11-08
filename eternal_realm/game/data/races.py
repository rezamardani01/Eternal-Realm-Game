"""Playable races: innate stat shifts plus per-activity reward multipliers.

Every race has a strength and a weakness, no race is the best at everything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .stats import Stats


@dataclass(frozen=True)
class Race:
    id: str
    emoji: str
    name: str
    description: str
    stats: Stats
    #: reward multiplier per activity id (missing = 1.0)
    perks: dict[str, float] = field(default_factory=dict)
    xp_multiplier: float = 1.0


RACES: dict[str, Race] = {
    r.id: r
    for r in (
        Race(
            "elf", "🌳", "الف جنگلی",
            "چابک و خوش‌شانس؛ استاد گیاه‌چینی",
            Stats(hp=-10, atk=1, defense=-1, magic=1, speed=4, luck=3),
            {"herb": 1.3, "hunt": 1.05},
        ),
        Race(
            "dwarf", "⛏️", "دورف",
            "سخت‌جان؛ استاد معدن‌کاری",
            Stats(hp=15, atk=1, defense=4, magic=-2, speed=-3, luck=0),
            {"mining": 1.3},
        ),
        Race(
            "fairy", "🧚", "پری",
            "جادویی و خوش‌اقبال؛ ظریف‌تن",
            Stats(hp=-12, atk=-2, defense=-1, magic=5, speed=2, luck=4),
            {"search": 1.2, "fishing": 1.1},
        ),
        Race(
            "dragonborn", "🐉", "اژدهازاد",
            "نیرومند و پرجان؛ شکارچی بزرگ",
            Stats(hp=10, atk=5, defense=1, magic=0, speed=-2, luck=-2),
            {"hunt": 1.2},
        ),
        Race(
            "shadowborn", "🌑", "سایه‌زاد",
            "سریع و مرموز؛ زره‌ی نازک",
            Stats(hp=-6, atk=2, defense=-2, magic=1, speed=5, luck=1),
            {"search": 1.15, "hunt": 1.1},
        ),
        Race(
            "human", "🧙", "انسان جادوآموخته",
            "متعادل؛ زودتر تجربه می‌گیرد",
            Stats(hp=2, atk=1, defense=1, magic=1, speed=1, luck=1),
            {"fishing": 1.05, "mining": 1.05, "herb": 1.05, "search": 1.05, "hunt": 1.05},
            xp_multiplier=1.05,
        ),
    )
}

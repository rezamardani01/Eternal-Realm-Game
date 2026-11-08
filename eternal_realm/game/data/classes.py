"""Combat classes: starting stats, per-level growth and one signature skill."""

from __future__ import annotations

from dataclasses import dataclass

from .stats import Stats


@dataclass(frozen=True)
class Skill:
    name: str
    emoji: str
    #: "phys" scales with attack, "magic" with the magic stat
    kind: str
    power: float
    cooldown: int
    #: none | pierce (ignores defence) | crit (guaranteed critical) | guard (also raises a shield)
    effect: str = "none"


@dataclass(frozen=True)
class CharacterClass:
    id: str
    emoji: str
    name: str
    description: str
    stats: Stats
    #: gained per level above the first (floats, rounded after summing)
    growth: tuple[float, float, float, float, float, float]
    skill: Skill
    crit_bonus: float = 0.0


CLASSES: dict[str, CharacterClass] = {
    c.id: c
    for c in (
        CharacterClass(
            "warrior", "⚔️", "جنگجو",
            "پرجان و قدرتمند در نبرد تن‌به‌تن",
            Stats(hp=20, atk=4, defense=3, magic=-2, speed=0, luck=0),
            (14, 2.2, 1.6, 0.4, 0.6, 0.2),
            Skill("ضربه سنگین", "💥", "phys", 1.7, 3),
        ),
        CharacterClass(
            "mage", "🔮", "جادوگر",
            "جادوی ویرانگر؛ دفاع کم",
            Stats(hp=-5, atk=-2, defense=-1, magic=9, speed=1, luck=1),
            (9, 0.6, 0.9, 2.8, 0.8, 0.4),
            Skill("گلوله آتشین", "🔥", "magic", 1.8, 3, "pierce"),
        ),
        CharacterClass(
            "archer", "🏹", "کماندار",
            "سریع و دقیق؛ تیر زره‌شکن",
            Stats(hp=0, atk=3, defense=0, magic=0, speed=4, luck=1),
            (10, 1.9, 1.0, 0.6, 1.4, 0.4),
            Skill("تیر دقیق", "🎯", "phys", 1.4, 3, "pierce"),
        ),
        CharacterClass(
            "guardian", "🛡️", "نگهبان",
            "دیوار گروه؛ دفاع بالا",
            Stats(hp=30, atk=0, defense=6, magic=-2, speed=-2, luck=0),
            (16, 1.2, 2.2, 0.4, 0.4, 0.2),
            Skill("دیوار آهنین", "🧱", "phys", 0.9, 3, "guard"),
        ),
        CharacterClass(
            "rogue", "🗡️", "سایه‌رو",
            "سریع و کشنده؛ ضربه‌ی کاری",
            Stats(hp=-5, atk=2, defense=-1, magic=0, speed=6, luck=3),
            (9, 1.8, 0.8, 0.4, 1.6, 0.6),
            Skill("ضربه سایه", "🌑", "phys", 1.3, 3, "crit"),
            crit_bonus=0.08,
        ),
    )
}

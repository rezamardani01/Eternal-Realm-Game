"""Hunt monsters. Their strength is derived from the hunter's level, so a hunt is always a fair fight."""

from __future__ import annotations

from dataclasses import dataclass

from ..engine.combat import Fighter
from .activities import Drop


#: global knob: 1.0 = monsters equal an average hero of the same level without gear
DIFFICULTY = 1.15


@dataclass(frozen=True)
class Monster:
    id: str
    name: str
    emoji: str
    min_level: int
    #: share of an "average hero of that level" for each stat
    hp: float
    atk: float
    defense: float
    speed: float
    xp: tuple[int, int]
    gold: tuple[int, int]
    drops: tuple[Drop, ...] = ()
    weight: int = 10
    max_level: int = 999

    def fighter(self, level: int) -> Fighter:
        """The monster as a fighter for a hero of ``level``."""
        hp = round((105 + 11.5 * (level - 1)) * self.hp * DIFFICULTY)
        atk = round((11 + 1.7 * (level - 1)) * self.atk * DIFFICULTY)
        defense = round((9 + 1.2 * (level - 1)) * self.defense)
        speed = round((10 + 0.9 * (level - 1)) * self.speed)
        return Fighter(
            name=self.name, emoji=self.emoji, max_hp=hp, hp=hp, atk=atk, defense=defense,
            magic=atk, speed=speed, luck=3, skill_name="حمله وحشیانه", skill_emoji="💢",
            skill_power=1.3, skill_cooldown=4,
        )


MONSTERS: tuple[Monster, ...] = (
    Monster("goblin", "گابلین", "👺", 1, 0.55, 0.75, 0.55, 0.9, (14, 20), (6, 18),
            (Drop("monster_hide", (1, 2), 0.6),), 14, 12),
    Monster("wolf", "گرگ وحشی", "🐺", 1, 0.65, 0.85, 0.5, 1.2, (16, 22), (4, 14),
            (Drop("monster_hide", (1, 1), 0.7), Drop("monster_fang", (1, 1), 0.3)), 14, 15),
    Monster("skeleton", "اسکلت جنگجو", "💀", 4, 0.85, 0.85, 0.8, 0.9, (20, 28), (10, 28),
            (Drop("monster_fang", (1, 1), 0.4), Drop("old_scroll", (1, 1), 0.15)), 12),
    Monster("orc", "اورک غران", "👹", 8, 1.05, 0.95, 0.8, 0.9, (28, 38), (18, 45),
            (Drop("iron_ore", (1, 3), 0.5), Drop("monster_fang", (1, 2), 0.5)), 10),
    Monster("golem", "گولم یخی", "🧊", 14, 1.3, 0.8, 1.1, 0.7, (38, 50), (30, 70),
            (Drop("crystal_shard", (1, 1), 0.2), Drop("stone", (2, 4), 0.8)), 8),
    Monster("whelp", "بچه‌اژدها", "🐲", 20, 1.2, 1.0, 0.95, 1.0, (55, 75), (50, 120),
            (Drop("dragon_scale", (1, 1), 0.12), Drop("crystal_shard", (1, 1), 0.3)), 6),
)

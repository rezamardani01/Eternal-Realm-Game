"""Companion pets. They add a small stat bonus to their owner; coin pets are cheap, premium pets are rarer.

Pet bonuses stay far below what good gear gives, so nobody is shut out of the main competition.
"""

from __future__ import annotations

from dataclasses import dataclass

from .stats import Stats


@dataclass(frozen=True)
class Pet:
    id: str
    emoji: str
    name: str
    rarity: int
    story: str
    bonus: Stats
    #: gold price for pets sold by the pet keeper (0 = premium only)
    price_gold: int = 0
    #: premium pack that sells this pet ("" = coins only)
    pack_id: str = ""


PETS: tuple[Pet, ...] = (
    Pet("cat", "🐱", "گربه‌ی چابک", 2, "گربه‌ای خیابانی که هر شب روی بام‌ها می‌دود و از هیچ سایه‌ای نمی‌ترسد.",
        Stats(speed=3, luck=2), price_gold=2500),
    Pet("hawk", "🦅", "شاهین نگهبان", 3, "از آسمان همه‌چیز را می‌بیند و پیش از دشمن خبر می‌دهد.",
        Stats(atk=3, speed=2), price_gold=4500),
    Pet("fox", "🦊", "روباه آتشین", 4, "دمش مثل شعله می‌درخشد و جادو دور و برش می‌رقصد.",
        Stats(magic=6, luck=4), pack_id="pet_fox"),
    Pet("wolf", "🐺", "گرگ سپیده", 4, "گرگی سپیدموی که با اولین نور صبح زوزه می‌کشد و یاران را دلگرم می‌کند.",
        Stats(atk=7, hp=40), pack_id="pet_wolf"),
    Pet("phoenix", "🔥", "ققنوس کوچک", 5, "جوجه‌ای از خاکستر که هر بار زخمی شود، دوباره گرم و زنده می‌شود.",
        Stats(hp=120, magic=8, defense=3), pack_id="pet_phoenix"),
)

_BY_ID = {p.id: p for p in PETS}


def get_pet(pet_id: str) -> Pet:
    return _BY_ID[pet_id]


MAX_PET_LEVEL = 10
#: each level adds this share of the pet's base bonus and of its strike power
LEVEL_STEP = 0.15


def upgrade_cost(level: int) -> int:
    """Crystals needed to go from ``level`` to the next one."""
    return 5 * level


def bonus_at(pet: Pet, level: int) -> Stats:
    return pet.bonus.scaled(1 + LEVEL_STEP * (level - 1))

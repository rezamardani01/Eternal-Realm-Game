"""Group bosses, generated from elements x archetypes (70 different bosses).

Adding a new element or archetype multiplies the roster; nothing here is listed by hand.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Element:
    id: str
    emoji: str
    adjective: str  # used after the archetype: «اژدهای آتشین»
    noun: str  # «آتش»
    special: str  # the boss's special move
    weak_class: str  # this class deals extra damage to bosses of the element
    hp_mod: float = 1.0
    atk_mod: float = 1.0
    level_offset: int = 0


@dataclass(frozen=True)
class Archetype:
    id: str
    emoji: str
    prefix: str  # the noun, already joined to its adjective: «اژدهای», «غول»
    base_level: int
    hp_factor: float
    atk_factor: float
    story: str


@dataclass(frozen=True)
class BossType:
    id: str
    emoji: str
    name: str
    min_level: int
    hp_factor: float
    atk_factor: float
    story: str
    element: Element
    special: str
    weak_class: str


ELEMENTS: tuple[Element, ...] = (
    Element("fire", "🔥", "آتشین", "آتش", "نفس آتشین", "archer", 1.0, 1.04, 0),
    Element("ice", "❄️", "یخی", "یخ", "طوفان یخ", "mage", 1.06, 0.97, 1),
    Element("lightning", "⚡", "رعدآسا", "رعد و برق", "صاعقه‌ی مرگبار", "guardian", 0.97, 1.05, 2),
    Element("nature", "🌿", "جنگلی", "طبیعت", "تازیانه‌ی ریشه‌ها", "warrior", 1.05, 0.98, 3),
    Element("water", "🌊", "دریایی", "آب", "موج غرق‌کننده", "rogue", 1.03, 1.0, 4),
    Element("shadow", "🌑", "سایه‌ای", "سایه", "هجوم تاریکی", "mage", 0.95, 1.07, 5),
    Element("earth", "🪨", "سنگی", "خاک", "لرزه‌ی زمین", "rogue", 1.08, 0.95, 6),
    Element("wind", "🌪️", "طوفانی", "باد", "گردباد", "archer", 0.96, 1.03, 7),
    Element("light", "✨", "نورانی", "نور", "پرتو سوزان", "rogue", 1.0, 1.0, 8),
    Element("poison", "☠️", "زهرآگین", "زهر", "ابر مسموم", "guardian", 0.98, 1.06, 9),
)

ARCHETYPES: tuple[Archetype, ...] = (
    Archetype("beast", "🐗", "هیولای", 3, 1.2, 1.1, "هیولایی وحشی از دل سرزمین‌های ناشناخته بیرون آمده است."),
    Archetype("giant", "🗿", "غول", 4, 1.3, 1.15, "غولی عظیم برخاسته و زمین زیر پایش می‌لرزد."),
    Archetype("spider", "🕷️", "عنکبوت", 8, 1.0, 1.0, "عنکبوتی غول‌پیکر با تارهای مرگبار از غار بیرون خزیده است."),
    Archetype("serpent", "🐍", "مار", 11, 1.05, 1.0, "ماری غول‌پیکر از اعماق باتلاق سر برآورده است."),
    Archetype("golem", "🧱", "گولم", 14, 1.4, 0.9, "گولمی سنگین‌وزن و تقریباً نابودنشدنی به راه افتاده است."),
    Archetype("wraith", "👻", "شبح", 18, 0.9, 1.2, "شبحی خشمگین از گورستان‌های باستانی برخاسته است."),
    Archetype("dragon", "🐉", "اژدهای", 25, 1.05, 0.95, "اژدهایی باستانی از خوابی هزارساله بیدار شده است."),
)


def _build() -> tuple[BossType, ...]:
    bosses = []
    for arch in ARCHETYPES:
        for el in ELEMENTS:
            bosses.append(
                BossType(
                    id=f"{arch.id}_{el.id}", emoji=arch.emoji, name=f"{arch.prefix} {el.adjective}",
                    min_level=arch.base_level + el.level_offset, hp_factor=round(arch.hp_factor * el.hp_mod, 3),
                    atk_factor=round(arch.atk_factor * el.atk_mod, 3),
                    story=f"{arch.story} نیروی {el.noun} در وجودش می‌جوشد.", element=el, special=el.special,
                    weak_class=el.weak_class,
                )
            )
    return tuple(sorted(bosses, key=lambda b: (b.min_level, b.id)))


BOSSES: tuple[BossType, ...] = _build()
_BY_ID = {b.id: b for b in BOSSES}


#: archetype -> (behaviour id, one-line description shown when the fight starts)
BEHAVIORS: dict[str, tuple[str, str]] = {
    "spider": ("hunter", "شکارچی است و همیشه ضعیف‌ترین جنگجو را نشانه می‌گیرد."),
    "serpent": ("healer", "می‌تواند چند بار زخم‌هایش را ببندد."),
    "wraith": ("berserk", "هرچه زخمی‌تر شود، خشمگین‌تر می‌شود."),
}


#: element -> the class whose blows the boss shrugs off a little (the weak class hits it harder)
ELEMENT_RESIST: dict[str, str] = {
    "fire": "guardian", "ice": "warrior", "lightning": "rogue", "nature": "mage", "water": "archer",
    "shadow": "warrior", "earth": "mage", "wind": "guardian", "light": "archer", "poison": "mage",
}
#: element -> harmful effects the boss cannot be given at all
ELEMENT_IMMUNE: dict[str, tuple[str, ...]] = {
    "fire": ("burn",), "ice": ("freeze",), "lightning": ("shock",), "nature": ("poison",), "water": ("burn",),
    "shadow": ("bleed",), "earth": ("freeze", "shock"), "wind": ("slow",), "light": ("burn", "bleed"), "poison": ("poison",),
}
#: element -> the exclusive piece of war gear its bosses drop
ELEMENT_DROP: dict[str, str] = {
    "fire": "b_fire", "ice": "b_ice", "lightning": "b_lightning", "nature": "b_nature", "water": "b_water",
    "shadow": "b_shadow", "earth": "b_earth", "wind": "b_wind", "light": "b_light", "poison": "b_poison",
}
#: chance that the top fighter finds the element piece, by tier (the others get a fifth of it)
DROP_CHANCE = {"weak": 0.15, "normal": 0.25, "strong": 0.35, "enraged": 0.50, "legend": 0.70}
#: a legendary boss may also drop one of these
MYTHIC_DROPS = ("doom_blade", "eternity_plate", "first_crown")
MYTHIC_CHANCE = 0.10
#: the announcement of each phase of the fight
PHASES = {
    2: "⚡ {name} وارد فاز دوم شد! تندتر و خطرناک‌تر می‌جنگد",
    3: "☠️ {name} وارد فاز سوم شد! دیگر چیزی برای از دست دادن ندارد و با همه‌ی توانش می‌کوبد",
}


def behavior_of(kind: "BossType") -> tuple[str, str]:
    archetype = kind.id.split("_")[0]
    return BEHAVIORS.get(archetype, ("normal", "در نیمه‌ی نبرد وارد فاز دوم می‌شود و تند و تیزتر می‌جنگد."))


def boss_by_id(boss_id: str) -> BossType:
    return _BY_ID[boss_id]


@dataclass(frozen=True)
class Tier:
    """How strong this particular summoning turned out to be. Rolled once per boss, revealed when the fight starts."""

    id: str
    emoji: str
    name: str
    weight: int
    hp: float
    atk: float
    #: multiplier of the victory rewards (a harder boss pays more)
    reward: float


TIERS: tuple[Tier, ...] = (
    Tier("weak", "🟢", "ضعیف", 6, 1.0, 1.0, 0.8),
    Tier("normal", "🔵", "معمولی", 20, 1.2, 1.1, 1.0),
    Tier("strong", "🟣", "قدرتمند", 32, 1.45, 1.22, 1.3),
    Tier("enraged", "🟠", "خشمگین", 26, 1.75, 1.35, 1.7),
    Tier("legend", "🔴", "افسانه‌ای", 16, 2.1, 1.5, 2.4),
)
_TIER_BY_ID = {t.id: t for t in TIERS}
#: the squad strength (stats compared with a plain character of the same level) that the tiers were balanced for
REFERENCE_POWER = 1.3


def tier_by_id(tier_id: str | None) -> Tier:
    return _TIER_BY_ID.get(tier_id or "", _TIER_BY_ID["normal"])


def roll_tier(rng: random.Random) -> Tier:
    return rng.choices(TIERS, weights=[t.weight for t in TIERS], k=1)[0]


def squad_scaling(power: float, fighters: int) -> tuple[float, float]:
    """(hp, attack) multipliers that keep the odds about the same for a well-geared squad as for a plain one.

    ``power`` is the squad's strength relative to a plain character; more fighters make the boss hit a bit harder.
    """
    rel = max(0.5, min(2.5, power / REFERENCE_POWER))
    return rel**1.1, rel**0.9 * (1 + 0.10 * max(0, fighters - 3))


def pick_boss(level: int, rng: random.Random) -> BossType:
    """A random boss fitting the summoner's level: at most 10 levels below it, never above it."""
    fitting = [b for b in BOSSES if level - 10 <= b.min_level <= level] or [BOSSES[0]]
    return rng.choice(fitting)


def boss_max_hp(kind: BossType, fighters: int, avg_level: int) -> int:
    return round(fighters * (95 + 56 * avg_level) * kind.hp_factor * 0.85)


def boss_attack(kind: BossType, avg_level: int) -> int:
    return round((7.5 + 1.75 * avg_level) * kind.atk_factor)


def boss_defense(avg_level: int) -> int:
    return round(4 + 0.8 * avg_level)

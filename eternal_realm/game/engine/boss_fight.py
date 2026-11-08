"""The automatic boss fight: one call plays one round for every fighter and for the boss.

Pure logic. Each class behaves in its own way, and a few rare events keep fights lively.
Events are returned as ``(priority, text)``: higher priority = more worth showing in the report.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ...shared.text import fa

Event = tuple[int, str]
NORMAL, NOTABLE, MAJOR = 1, 2, 3


@dataclass
class Hero:
    pid: int
    name: str
    class_id: str
    hp: int
    max_hp: int
    atk: int
    defense: int
    magic: int
    speed: int
    luck: int
    alive: bool = True
    damage: int = 0
    absorbed: int = 0
    shield: bool = False


@dataclass
class Boss:
    name: str
    hp: int
    max_hp: int
    atk: int
    defense: int
    round: int = 0
    enraged: bool = False
    weak: int = 0
    special: str = "مهارت ویژه"
    weak_class: str = ""


def _offense(hero: Hero) -> float:
    return max(hero.atk, hero.magic * 0.8)


def _hero_turn(hero: Hero, boss: Boss, team: list[Hero], rng: random.Random) -> list[Event]:
    events: list[Event] = []
    defense = boss.defense * (0.6 if boss.weak > 0 else 1.0)
    crit_chance = min(0.5, 0.05 + hero.luck * 0.003)
    base = _offense(hero) * rng.uniform(0.9, 1.1)
    mult, text, priority = 1.0, f"{hero.name} به باس ضربه زد", NORMAL
    if hero.class_id == boss.weak_class:
        mult = 1.2  # the boss's element is weak against this class

    if hero.class_id == "warrior":
        if rng.random() < 0.20:
            mult, text, priority = mult * 1.6, f"{hero.name} با شمشیر ضربه‌ای سنگین به باس وارد کرد", NOTABLE
        else:
            text = f"{hero.name} با شمشیر به باس حمله کرد"
    elif hero.class_id == "mage":
        mult, defense = mult * 1.25, defense * 0.7
        text = f"{hero.name} با جادوی آتشین، بدن باس را سوزاند"
    elif hero.class_id == "archer":
        mult, text = mult * 1.2, f"{hero.name} چند تیر پیاپی به باس زد"
    elif hero.class_id == "rogue":
        crit_chance += 0.25
        text = f"{hero.name} از پشت و غافلگیرانه ضربه زد"
    elif hero.class_id == "guardian":
        mult, text = mult * 0.6, f"{hero.name} سپر را بالا برد و ضربه زد"
        allies = [h for h in team if h.alive and h is not hero and not h.shield]
        if allies and rng.random() < 0.40:
            ally = rng.choice(allies)
            ally.shield = True
            hero.absorbed += max(5, round(boss.atk * 0.4))
            events.append((NOTABLE, f"🛡️ {hero.name} جلوی ضربه‌ی باس را برای {ally.name} گرفت"))

    if rng.random() < 0.08:
        events.append((NORMAL, f"💨 ضربه‌ی {hero.name} به هدف نخورد"))
        return events
    crit = rng.random() < crit_chance
    if rng.random() < 0.05:
        mult *= 2.0
        boss.weak = 2
        events.append((MAJOR, f"🎯 {hero.name} نقطه‌ی ضعف باس را پیدا کرد! باس برای دو دور ضعیف شد"))
    amount = max(1, round(base * mult * (1.5 if crit else 1.0) - defense * 0.5))
    amount = min(amount, boss.hp)
    boss.hp -= amount
    hero.damage += amount
    marker = "ضربه‌ی کاری! " if crit else ""
    events.append((max(priority, NOTABLE if crit else NORMAL), f"⚔️ {marker}{text} ({fa(amount)} آسیب)"))
    return events


def _hit_hero(boss: Boss, hero: Hero, power: float, rng: random.Random, label: str) -> list[Event]:
    if rng.random() < min(0.20, hero.speed * 0.004):
        return [(NORMAL, f"💨 {hero.name} از ضربه‌ی باس جاخالی داد")]
    raw = boss.atk * power * (1.5 if boss.enraged else 1.0) * rng.uniform(0.9, 1.1)
    amount = max(1, round(raw - hero.defense * 0.5))
    if hero.shield:
        hero.shield = False
        amount = max(1, amount // 2)
    amount = min(amount, hero.hp)
    hero.hp -= amount
    events: list[Event] = [(NORMAL, f"🩸 {label} {hero.name} ({fa(amount)} آسیب)")]
    if hero.hp <= 0:
        hero.alive = False
        events.append((MAJOR, f"💀 {hero.name} از پا افتاد"))
    return events


def _boss_turn(boss: Boss, heroes: list[Hero], rng: random.Random) -> list[Event]:
    alive = [h for h in heroes if h.alive]
    if not alive or boss.hp <= 0:
        return []
    events: list[Event] = []
    if not boss.enraged and boss.hp < boss.max_hp * 0.30:
        boss.enraged = True
        events.append((MAJOR, f"🔥 {boss.name} وارد حالت خشم شد! حمله‌هایش سنگین‌تر می‌شود"))
    roll = rng.random()
    if roll < 0.45:
        events += _boss_single(boss, alive, rng)
    elif roll < 0.65:
        for target in rng.sample(alive, min(len(alive), rng.randint(2, 3))):
            events += _hit_hero(boss, target, 0.8, rng, f"{boss.name} با چنگال به")
    elif roll < 0.77:
        events.append((NOTABLE, f"🌪️ {boss.name} حمله‌ی گروهی زد!"))
        for target in alive:
            events += _hit_hero(boss, target, 0.45, rng, "موج حمله به")
    elif roll < 0.90:
        target = rng.choice(alive)
        events.append((NOTABLE, f"💢 {boss.name} با چرخشی سهمگین به {target.name} حمله کرد!"))
        events += _hit_hero(boss, target, 1.8, rng, "ضربه‌ی سنگین به")
    else:
        events.append((NOTABLE, f"✨ {boss.name} «{boss.special}» را فعال کرد!"))
        for target in rng.sample(alive, min(len(alive), 2)):
            events += _hit_hero(boss, target, 1.4, rng, "مهارت ویژه به")
    return events


def _boss_single(boss: Boss, alive: list[Hero], rng: random.Random) -> list[Event]:
    target = rng.choice(alive)
    return _hit_hero(boss, target, 1.0, rng, f"{boss.name} به")


def run_round(boss: Boss, heroes: list[Hero], rng: random.Random) -> list[Event]:
    """Play one round: every living fighter acts (fastest first), then the boss answers."""
    boss.round += 1
    events: list[Event] = []
    for hero in sorted((h for h in heroes if h.alive), key=lambda h: -h.speed):
        if boss.hp <= 0:
            break
        events += _hero_turn(hero, boss, heroes, rng)
    if boss.hp > 0:
        events += _boss_turn(boss, heroes, rng)
    if boss.weak > 0:
        boss.weak -= 1
    return events


def is_over(boss: Boss, heroes: list[Hero]) -> str | None:
    """``'won'`` / ``'lost'`` when the fight has ended, else ``None``."""
    if boss.hp <= 0:
        return "won"
    if not any(h.alive for h in heroes):
        return "lost"
    return None

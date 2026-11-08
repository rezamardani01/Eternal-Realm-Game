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
    #: how many fallen friends this hero can still bring back (mages and guardians)
    revive: int = 1
    #: the boss froze this hero's hands: the next turn is lost
    stunned: bool = False


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
    #: normal | hunter (picks the weakest hero) | healer (mends itself) | berserk (angrier the more hurt)
    behavior: str = "normal"
    phase: int = 1
    heals_left: int = 3
    #: rounds during which a warrior is holding the boss down (mages hit harder)
    pinned: int = 0
    #: how many times chaos may still let the boss regrow some health
    surges: int = 3


def _offense(hero: Hero) -> float:
    return max(hero.atk, hero.magic * 0.8)


def _try_revive(hero: Hero, team: list[Hero], rng: random.Random) -> list[Event] | None:
    """A mage or guardian may spend their turn raising a fallen friend."""
    if hero.class_id not in ("mage", "guardian") or hero.revive <= 0:
        return None
    fallen = [h for h in team if not h.alive]
    if not fallen or rng.random() >= 0.35:
        return None
    friend = rng.choice(fallen)
    hero.revive -= 1
    friend.alive = True
    friend.hp = max(1, round(friend.max_hp * 0.4))
    how = "با طلسم نور" if hero.class_id == "mage" else "با سپر مقدس"
    return [(MAJOR, f"✨ {hero.name} {how} {friend.name} را به میدان برگرداند!")]


def _hero_turn(hero: Hero, boss: Boss, team: list[Hero], rng: random.Random) -> list[Event]:
    events: list[Event] = []
    revived = _try_revive(hero, team, rng)
    if revived is not None:
        return revived
    defense = boss.defense * (0.6 if boss.weak > 0 else 1.0)
    crit_chance = min(0.5, 0.05 + hero.luck * 0.003)
    base = _offense(hero) * rng.uniform(0.9, 1.1)
    mult, text, priority = 1.0, f"{hero.name} به باس ضربه زد", NORMAL
    if hero.class_id == boss.weak_class:
        mult = 1.2  # the boss's element is weak against this class

    if hero.class_id == "warrior":
        if rng.random() < 0.20:
            mult, text, priority = mult * 1.6, f"{hero.name} با شمشیر ضربه‌ای سنگین به باس وارد کرد", NOTABLE
        elif boss.pinned <= 0 and rng.random() < 0.25 and any(h.alive and h.class_id == "mage" for h in team):
            boss.pinned = 2
            events.append((NOTABLE, f"🤝 {hero.name} باس را مهار کرد؛ جادوگران فرصت طلایی دارند!"))
            text = f"{hero.name} با شمشیر حمله کرد"
        else:
            text = f"{hero.name} با شمشیر به باس حمله کرد"
    elif hero.class_id == "mage":
        mult, defense = mult * 1.25, defense * 0.7
        text = f"{hero.name} با جادوی آتشین، بدن باس را سوزاند"
        if boss.pinned > 0:
            mult *= 1.4
            text = f"{hero.name} با طلسم ترکیبی، باس مهارشده را سوزاند"
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
    rage = 1.0 + (1 - boss.hp / max(boss.max_hp, 1)) * 0.5 if boss.behavior == "berserk" else 1.0
    deadly = rng.random() < 0.08  # luck: sometimes the boss lands a monstrous blow
    raw = boss.atk * power * rage * (1.5 if boss.enraged else 1.0) * rng.uniform(0.9, 1.1) * (1.6 if deadly else 1.0)
    amount = max(1, round(raw - hero.defense * 0.5))
    if hero.shield:
        hero.shield = False
        amount = max(1, amount // 2)
    amount = min(amount, hero.hp)
    hero.hp -= amount
    events: list[Event] = [(NOTABLE if deadly else NORMAL, f"{'☠️ ضربه‌ی مرگبار! ' if deadly else '🩸 '}{label} {hero.name} ({fa(amount)} آسیب)")]
    if hero.hp <= 0:
        hero.alive = False
        events.append((MAJOR, f"💀 {hero.name} از پا افتاد"))
    return events


def _boss_turn(boss: Boss, heroes: list[Hero], rng: random.Random) -> list[Event]:
    alive = [h for h in heroes if h.alive]
    if not alive or boss.hp <= 0:
        return []
    events: list[Event] = []
    if boss.phase == 1 and boss.hp < boss.max_hp * 0.50:
        boss.phase = 2
        boss.atk = round(boss.atk * 1.15)
        events.append((MAJOR, f"⚡ {boss.name} وارد فاز دوم شد! تندتر و خطرناک‌تر می‌جنگد"))
    if boss.behavior == "healer" and boss.heals_left > 0 and boss.round % 3 == 0 and boss.hp < boss.max_hp:
        boss.heals_left -= 1
        mended = min(boss.max_hp - boss.hp, round(boss.max_hp * 0.05))
        boss.hp += mended
        events.append((NOTABLE, f"💚 {boss.name} زخم‌هایش را بست و {fa(mended)} جان گرفت"))
    if not boss.enraged and boss.hp < boss.max_hp * 0.30:
        boss.enraged = True
        events.append((MAJOR, f"🔥 {boss.name} وارد حالت خشم شد! حمله‌هایش سنگین‌تر می‌شود"))
    roll = rng.random()
    if boss.phase >= 2 and roll < 0.08:
        roll = 0.95  # in phase two the special move comes more often
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
    if boss.behavior == "hunter":
        target = min(alive, key=lambda h: h.hp / max(h.max_hp, 1))
    else:
        target = rng.choice(alive)
    return _hit_hero(boss, target, 1.0, rng, f"{boss.name} به")


def _chaos(boss: Boss, heroes: list[Hero], rng: random.Random) -> list[Event]:
    """Luck of the fight: the boss may stun a fighter or draw fresh strength from the earth."""
    events: list[Event] = []
    alive = [h for h in heroes if h.alive and not h.stunned]
    if len(alive) > 1 and rng.random() < 0.07:
        victim = rng.choice(alive)
        victim.stunned = True
        events.append((NOTABLE, f"💫 {boss.name} نعره‌ای زد و {victim.name} را گیج کرد"))
    if boss.surges > 0 and boss.hp < boss.max_hp * 0.8 and rng.random() < 0.06:
        boss.surges -= 1
        mended = min(boss.max_hp - boss.hp, round(boss.max_hp * 0.04))
        boss.hp += mended
        events.append((NOTABLE, f"🌋 {boss.name} از زمین نیرو گرفت و {fa(mended)} جان بازیافت"))
    return events


def run_round(boss: Boss, heroes: list[Hero], rng: random.Random) -> list[Event]:
    """Play one round: every living fighter acts (fastest first), then the boss answers."""
    boss.round += 1
    events: list[Event] = []
    for hero in sorted((h for h in heroes if h.alive), key=lambda h: -h.speed):
        if boss.hp <= 0:
            break
        if hero.stunned:
            hero.stunned = False
            events.append((NORMAL, f"💫 {hero.name} هنوز گیج است و نوبتش را از دست داد"))
            continue
        events += _hero_turn(hero, boss, heroes, rng)
    if boss.hp > 0:
        events += _chaos(boss, heroes, rng)
        events += _boss_turn(boss, heroes, rng)
    if boss.weak > 0:
        boss.weak -= 1
    if boss.pinned > 0:
        boss.pinned -= 1
    return events


def is_over(boss: Boss, heroes: list[Hero]) -> str | None:
    """``'won'`` / ``'lost'`` when the fight has ended, else ``None``."""
    if boss.hp <= 0:
        return "won"
    if not any(h.alive for h in heroes):
        return "lost"
    return None

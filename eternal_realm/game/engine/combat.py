"""Turn-based combat between two fighters (pure logic, serialisable, deterministic per RNG).

The same engine drives duels (humans pick actions), team fights, solo fights and hunts (the AI picks them).

A hero fights with a basic attack, three skills of his own (see ``data/skills.py``, each with a cooldown counted in his
own turns), a defence, and up to four pieces of war gear (``data/arms.py``) whose *traits* are read here: critical
strikes, life steal, thorns, extra hits, poison and the rest. Monsters keep the single legacy skill. Everything is
computed on the server, from the numbers saved in the fighter, never from anything a player sends.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from ...shared.text import fa
from ..data.arms import CAPS, RATING
from ..data.classes import CharacterClass
from ..data.growth import SKILL_LEVELS
from ..data.skills import CLASS_SKILLS, DOTS, EFFECT_INFO, HARMFUL, TICKING, Effect, HeroSkill, skills_for
from ..data.stats import Stats

#: traits whose strength lives in the chance (the rest in the value)
CHANCE_KINDS = ("extra_hit", "cd_cut")


class Action(StrEnum):
    ATTACK = "attack"
    #: the legacy single skill; for a hero it is his third (signature) skill
    SKILL = "skill"
    SKILL1 = "skill1"
    SKILL2 = "skill2"
    SKILL3 = "skill3"
    DEFEND = "defend"
    SURRENDER = "surrender"


SKILL_ACTIONS = {Action.SKILL1: 0, Action.SKILL2: 1, Action.SKILL3: 2}


@dataclass
class Fighter:
    name: str
    emoji: str
    max_hp: int
    hp: int
    atk: int
    defense: int
    magic: int
    speed: int
    luck: int
    skill_name: str = "ضربه ویژه"
    skill_emoji: str = "💥"
    skill_kind: str = "phys"
    skill_power: float = 1.5
    skill_cooldown: int = 3
    skill_effect: str = "none"
    crit_bonus: float = 0.0
    skill_ready_in: int = 0
    shield: bool = False
    player_id: int | None = None
    mention: str = ""
    #: a companion that sometimes joins an attack: emoji, name, strike power (0 = none)
    pet_emoji: str = ""
    pet_name: str = ""
    pet_power: int = 0
    #: the hero's three skills (``HeroSkill.to_dict``); empty for a monster, who uses the legacy skill above
    skills: list[dict] = field(default_factory=list)
    #: turns until each of the three skills is ready again (see :func:`skill_wait`)
    cds: list[int] = field(default_factory=list)
    #: traits of the equipped gear: ``{"k": kind, "v": value, "c": chance, "t": turns}``
    traits: list[dict] = field(default_factory=list)
    #: effects sitting on this fighter: ``{"k": kind, "t": turns left, "v": strength}``
    statuses: list[dict] = field(default_factory=list)
    #: what the gear adds to the "how strong is this fighter" number
    trait_power: int = 0
    undying_used: bool = False
    stand_used: bool = False
    #: for each of the three skills the hero level that opens it while it is still closed (0 = open)
    lock: list[int] = field(default_factory=list)
    #: chance (0-1) to shrug off each kind of harmful effect; 1 = immune (bosses)
    resist: dict[str, float] = field(default_factory=dict)

    @property
    def hp_ratio(self) -> float:
        return self.hp / self.max_hp

    @property
    def skill_ready(self) -> bool:
        return self.skill_ready_in <= 0

    @property
    def has_skills(self) -> bool:
        return bool(self.skills)

    def skill_wait(self, index: int) -> int:
        """Turns this hero must still let pass before skill ``index`` (0-2) can be used; 0 = ready now."""
        return max(0, self.cds[index] - 1) if index < len(self.cds) else 0

    @classmethod
    def for_player(
        cls, player_id: int, name: str, char_class: CharacterClass, stats: Stats, mention: str = "",
        race_id: str = "", traits: tuple | list = (), level: int = 999,
    ) -> Fighter:
        skill = char_class.skill
        fighter = cls(
            name=name, emoji=char_class.emoji, max_hp=stats.hp, hp=stats.hp, atk=stats.atk,
            defense=stats.defense, magic=stats.magic, speed=stats.speed, luck=stats.luck,
            skill_name=skill.name, skill_emoji=skill.emoji, skill_kind=skill.kind,
            skill_power=skill.power, skill_cooldown=skill.cooldown, skill_effect=skill.effect,
            crit_bonus=char_class.crit_bonus, player_id=player_id, mention=mention,
        )
        if race_id and char_class.id in CLASS_SKILLS:
            fighter.skills = [s.to_dict() for s in skills_for(race_id, char_class.id)]
            fighter.cds = [0, 0, 0]
            fighter.lock = [need if level < need else 0 for need in SKILL_LEVELS]
            top = fighter.skills[2]  # the old single-skill fields describe the signature move
            fighter.skill_name, fighter.skill_emoji, fighter.skill_kind = top["name"], top["emoji"], top["kind"]
        fighter.traits = [{"k": t.k, "v": t.v, "c": t.c, "t": t.t} for t in traits]
        fighter.trait_power = trait_rating(fighter.traits)
        for t in fighter.traits:  # the opening rush starts with the fight
            if t["k"] == "opening":
                _apply(fighter, "atk_up", t["v"], t["t"])
        if _sum(fighter, "shield_start"):
            fighter.shield = True
        return fighter


def trait_rating(traits: list[dict]) -> int:
    total = 0.0
    for t in traits:
        k = t["k"]
        weight = RATING.get("inflict" if k.startswith("inflict_") else k, 0)
        if k in ("shield_start", "opening"):
            amount = 1.0
        elif k in CHANCE_KINDS or k.startswith("inflict_"):
            amount = t["c"]
        else:
            amount = t["v"]
        total += weight * amount
    return round(total)


# --- reading the gear and the effects of a fighter -------------------------------------------------------------------------
def _sum(f: Fighter, kind: str) -> float:
    """Total of one trait kind over the equipped gear, limited by the kind's cap."""
    total = sum(t["c"] if kind in CHANCE_KINDS else t["v"] for t in f.traits if t["k"] == kind)
    return min(total, CAPS[kind]) if kind in CAPS else total


def _status(f: Fighter, kind: str) -> dict | None:
    return next((s for s in f.statuses if s["k"] == kind and s["t"] > 0), None)


def _apply(f: Fighter, kind: str, value: float, turns: int) -> None:
    """Put an effect on a fighter (a repeated one is refreshed, never stacked). Modifiers last ``turns`` full turns."""
    keep = turns if kind in TICKING or kind == "freeze" else turns + 1
    current = _status(f, kind)
    if current:
        current["t"], current["v"] = max(current["t"], keep), max(current["v"], value)
    else:
        f.statuses.append({"k": kind, "t": keep, "v": value})


def _mod(f: Fighter, up: str, down: str) -> float:
    m = 1.0
    if (s := _status(f, up)):
        m *= 1 + s["v"]
    if (s := _status(f, down)):
        m *= max(0.1, 1 - s["v"])
    return m


def _shocked(f: Fighter) -> float:
    return max(0.1, 1 - s["v"]) if (s := _status(f, "shock")) else 1.0


def eff_atk(f: Fighter) -> float:
    return f.atk * _mod(f, "atk_up", "atk_down") * _shocked(f)


def eff_magic(f: Fighter) -> float:
    return f.magic * _mod(f, "atk_up", "atk_down") * _shocked(f)


def eff_defense(f: Fighter) -> float:
    low = 1 + _sum(f, "low_hp_def") if f.hp_ratio < 0.4 else 1.0
    return f.defense * _mod(f, "def_up", "def_down") * low


def eff_speed(f: Fighter) -> float:
    return f.speed * (1 - s["v"] if (s := _status(f, "slow")) else 1)


def status_line(f: Fighter) -> str:
    """Icons of what sits on a fighter right now, e.g. ``☠️۳ 🐌۲`` (the number is the turns left)."""
    parts = []
    for s in f.statuses:
        if s["t"] > 0 and s["k"] in EFFECT_INFO:
            left = s["t"] if s["k"] in TICKING or s["k"] == "freeze" else max(1, s["t"] - 1)
            parts.append(f"{EFFECT_INFO[s['k']][0]}{fa(left)}")
    if f.shield:
        parts.append("🛡️")
    return " ".join(parts)


@dataclass
class Battle:
    fighters: list[Fighter]
    actor: int = 0
    round: int = 1
    max_rounds: int = 15
    finished: bool = False
    #: index of the winning fighter, ``None`` for a draw (only meaningful when finished)
    winner: int | None = None
    surrendered: bool = False
    #: how much stronger the stronger fighter really was before the cap, and who it was (-1 = nobody)
    power_ratio: float = 1.0
    strong: int = -1

    # --- persistence --------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Battle:
        return cls(fighters=[Fighter(**f) for f in data["fighters"]], **{k: v for k, v in data.items() if k != "fighters"})

    # --- helpers ------------------------------------------------------------------------------
    @property
    def current(self) -> Fighter:
        return self.fighters[self.actor]

    @property
    def other(self) -> Fighter:
        return self.fighters[1 - self.actor]

    @classmethod
    def start(cls, a: Fighter, b: Fighter, max_rounds: int, rng: random.Random) -> Battle:
        """Faster fighter acts first; a tie is decided by a coin flip."""
        first = 0 if a.speed > b.speed else 1 if b.speed > a.speed else rng.randint(0, 1)
        return cls([a, b], actor=first, max_rounds=max_rounds)


#: in a fight between heroes the stronger side keeps at most this much of its advantage
PVP_CAP = 1.7
#: a companion's strike in a fight between heroes never exceeds this share of its owner's attack (plus a little)
PVP_PET_SHARE = 0.25


def power_of(f: Fighter) -> float:
    """One number for how strong a fighter is (hit points, attack, defence, magic, speed, luck, pet and gear traits)."""
    return f.max_hp / 4 + f.atk * 3 + f.defense * 2 + f.magic * 2.4 + f.speed + f.luck + f.pet_power * 2 + f.trait_power


def _shrink(f: Fighter, k: float) -> None:
    f.max_hp = max(1, round(f.max_hp * k))
    f.hp = min(f.max_hp, max(1, round(f.hp * k)))
    f.atk, f.defense, f.magic = max(1, round(f.atk * k)), round(f.defense * k), round(f.magic * k)
    f.speed, f.luck = max(1, round(f.speed * k)), round(f.luck * k)
    f.pet_power = round(f.pet_power * k)
    f.trait_power = round(f.trait_power * k)
    for t in f.traits:  # the gear's special powers shrink with the rest, so a lead can never grow past the cap
        t["v"], t["c"] = t["v"] * k, t["c"] * k if t["c"] < 1 and t["k"] != "opening" else t["c"]


def cap_pet(f: Fighter) -> None:
    if f.pet_power:
        f.pet_power = min(f.pet_power, round(f.atk * PVP_PET_SHARE) + 4)


def level_field(sides: list[list[Fighter]], cap: float = PVP_CAP) -> tuple[float, int]:
    """Cap the stronger side's advantage in a fight between heroes (companions are capped too).

    ``sides`` is a list of teams (a duel is two teams of one). Teams are compared by the average power of their
    members. Returns the real ratio before the cap and the index of the stronger team (``-1`` when equal)."""
    for side in sides:
        for f in side:
            cap_pet(f)
    powers = [sum(power_of(f) for f in side) / max(1, len(side)) for side in sides]
    high, low = max(powers), min(powers)
    if low <= 0 or high == low:
        return 1.0, -1
    ratio, strong = high / low, powers.index(high)
    if ratio > cap:
        for f in sides[strong]:
            _shrink(f, cap / ratio)
    return ratio, strong


def reward_factor(ratio: float, strong: bool) -> float:
    """What a win is worth: beating somebody much weaker pays little or nothing, beating somebody stronger pays more."""
    if strong:
        return 1.0 if ratio < 1.5 else 0.6 if ratio < 2 else 0.3 if ratio < 3 else 0.0
    return min(2.0, 1 + (ratio - 1) / 2)


# --- the damage formula -----------------------------------------------------------------------------------------------------
def _dodge_chance(actor: Fighter, target: Fighter) -> float:
    base = 0.03 + (eff_speed(target) - eff_speed(actor)) * 0.005
    return min(0.15, max(0.0, base)) + min(_sum(target, "evade"), CAPS["evade"])


def _crit_chance(actor: Fighter, target: Fighter | None = None) -> float:
    boost = s["v"] if (s := _status(actor, "crit_up")) else 0.0
    chance = min(0.6, 0.05 + actor.luck * 0.003 + actor.crit_bonus + _sum(actor, "crit_chance") + boost)
    return chance * (1 - _sum(target, "crit_resist")) if target is not None else chance


def _strike(
    actor: Fighter, target: Fighter, offense: float, defense: float, rng: random.Random,
    *, force_crit: bool = False, bonus: float = 1.0,
) -> tuple[int, bool]:
    """One blow: the offense (stat times skill power), the armour it meets, luck of ±10%, a possible critical hit.

    The target's shield halves it and its damage cut (gear) trims it; it is never below 1."""
    raw = offense * rng.uniform(0.9, 1.1) - defense
    crit = force_crit or rng.random() < _crit_chance(actor, target)
    if crit:
        raw *= 1.5 + _sum(actor, "crit_mult")
    raw *= bonus
    damage = max(1, round(raw))
    cut = _sum(target, "dmg_cut")
    if cut:
        damage = max(1, round(damage * (1 - cut)))
    if target.shield:
        damage = max(1, damage // 2)
        target.shield = False
    return damage, crit


def _fall(f: Fighter, lines: list[str]) -> None:
    """After a fighter lost hit points: a phoenix charm may raise him once, a last stand may heal him once."""
    if f.hp <= 0 and not f.undying_used and (v := _sum(f, "undying")):
        f.undying_used = True
        f.hp = max(1, round(f.max_hp * v))
        lines.append(f"🔥 {f.name} از خاکستر خود برخاست و با {fa(f.hp)} جان به نبرد برگشت!")
    elif 0 < f.hp < f.max_hp * 0.3 and not f.stand_used and (v := _sum(f, "last_stand")):
        f.stand_used = True
        heal = max(1, round(f.max_hp * v))
        f.hp = min(f.max_hp, f.hp + heal)
        lines.append(f"💖 {f.name} در لبه‌ی افتادن جان گرفت: {fa(heal)} جان برگشت!")


def _heal(f: Fighter, amount: int) -> int:
    amount = max(0, min(amount, f.max_hp - f.hp))
    f.hp += amount
    return amount


def _resist_chance(f: Fighter, kind: str) -> float:
    return min(1.0, _sum(f, "resist_all") + f.resist.get(kind, 0.0) + f.resist.get("all", 0.0))


def _inflict(
    me: Fighter, foe: Fighter, kind: str, value: float, turns: int, offense: float, lines: list[str],
    rng: random.Random | None = None,
) -> None:
    """Put an effect on the foe. Damage-over-time effects freeze their damage per turn when they are cast.

    The foe may resist it (gear, attribute points, the nature of a boss); an immune foe always does."""
    chance = _resist_chance(foe, kind)
    if chance >= 1.0 or (chance > 0 and rng is not None and rng.random() < chance):
        lines.append(f"🧿 {foe.name} در برابر «{EFFECT_INFO[kind][1]}» مقاومت کرد!")
        return
    if kind in DOTS:
        value = max(1, round(offense * value))
    elif kind == "stun":
        if not _status(foe, "stun"):
            foe.statuses.append({"k": "stun", "t": 1, "v": 0})
    if kind == "slow":
        foe.cds = [c + 1 if c > 0 else c for c in foe.cds]
        if foe.skill_ready_in > 0:
            foe.skill_ready_in += 1
    if kind != "stun":
        _apply(foe, kind, value, turns or 1)
    icon, name = EFFECT_INFO[kind]
    lines.append(f"{icon} {foe.name} {name} شد!")


def _on_hit(me: Fighter, foe: Fighter, damage: int, rng: random.Random, lines: list[str], foe_hp_before: int) -> None:
    """Everything the gear does for each successful blow."""
    heal = _sum(me, "leech_flat") + damage * _sum(me, "leech_pct") + min(
        foe_hp_before * _sum(me, "leech_foe_hp"), me.max_hp * 0.08
    )
    if heal >= 1 and me.hp < me.max_hp and me.hp > 0:
        got = _heal(me, round(heal))
        if got:
            lines.append(f"🩸 {me.name} {fa(got)} جان گرفت.")
    thorns = _sum(foe, "thorns")
    if thorns and damage > 1 and foe.hp > 0:
        back = max(1, round(damage * thorns))
        me.hp = max(0, me.hp - back)
        lines.append(f"🌵 خارها {fa(back)} آسیب به {me.name} برگرداندند.")
    if foe.hp > 0:
        offense = max(eff_atk(me), eff_magic(me) * 0.8)
        for t in me.traits:
            if t["k"].startswith("inflict_") and rng.random() < t["c"]:
                _inflict(me, foe, t["k"].split("_", 1)[1], t["v"], t["t"], offense, lines, rng)


PET_CHANCE = 0.30


def _pet_strike(me: Fighter, foe: Fighter, rng: random.Random, lines: list[str]) -> None:
    """The attacker's pet may jump in with a small extra hit, announced at that very moment."""
    if not me.pet_power or foe.hp <= 0 or rng.random() >= PET_CHANCE:
        return
    damage = max(1, round(me.pet_power * rng.uniform(0.9, 1.1) - foe.defense * 0.25))
    foe.hp = max(0, foe.hp - damage)
    lines.append(f"{me.pet_emoji} {me.pet_name} همراه {me.name} هم به {foe.name} حمله کرد! 💥 {fa(damage)} آسیب")


def _bonus(me: Fighter, foe: Fighter, effects: tuple | list = ()) -> float:
    """Extra damage multipliers: the finishing blow of a skill and the gear's executioner trait."""
    bonus = 1.0
    for e in effects:
        if e.k == "execute" and foe.hp_ratio < 0.4:
            bonus *= 1 + e.v
    if foe.hp_ratio < 0.3 and (v := _sum(me, "execute")):
        bonus *= 1 + v
    if (v := _sum(me, "backstab")) and any(s["k"] in HARMFUL and s["t"] > 0 for s in foe.statuses):
        bonus *= 1 + v
    return bonus


def _armor(me: Fighter, foe: Fighter, kind: str, pierce: bool) -> float:
    if pierce:
        return 0.0
    return eff_defense(foe) * (0.5 if kind == "phys" else 0.3) * (1 - _sum(me, "armor_pen"))


def _blow(me: Fighter, foe: Fighter, offense: float, kind: str, rng: random.Random, lines: list[str], *,
          pierce: bool = False, force_crit: bool = False, effects: tuple | list = (), power: float = 1.0,
          scale: str | None = None) -> tuple[int, bool]:
    foe_hp = foe.hp
    offense *= 1 + _sum(me, "magic_power" if (scale or kind) == "magic" else "phys_power")
    damage, crit = _strike(me, foe, offense * power, _armor(me, foe, kind, pierce), rng,
                           force_crit=force_crit, bonus=_bonus(me, foe, effects))
    foe.hp = max(0, foe.hp - damage)
    _on_hit(me, foe, damage, rng, lines, foe_hp)
    return damage, crit


def _extra_hit(me: Fighter, foe: Fighter, rng: random.Random, lines: list[str]) -> None:
    """Speed gear: after a blow, a chance to strike once more with half the strength."""
    chance = _sum(me, "extra_hit")
    if chance and foe.hp > 0 and me.hp > 0 and rng.random() < chance:
        offense = max(eff_atk(me), eff_magic(me) * 0.8)
        damage, crit = _blow(me, foe, offense, "phys", rng, lines, power=0.6,
                             scale="magic" if eff_magic(me) * 0.8 > eff_atk(me) else "phys")
        lines.append(f"⚡ {me.name} پیش از آن‌که {foe.name} نفس بکشد، ضربه‌ی دوم را زد! {'🎯 ' if crit else ''}💥 {fa(damage)} آسیب")


# --- the turn ------------------------------------------------------------------------------------------------------------------
def skill_of(f: Fighter, action: Action) -> tuple[int, HeroSkill] | None:
    """The hero skill an action stands for (the legacy ``SKILL`` is the third one); ``None`` for monsters."""
    if not f.skills or action not in (Action.SKILL, *SKILL_ACTIONS):
        return None
    index = SKILL_ACTIONS.get(action, 2)
    raw = f.skills[index]
    return index, HeroSkill(**{**raw, "effects": tuple(Effect(**e) if isinstance(e, dict) else e for e in raw["effects"])})


def readiness_error(f: Fighter, action: Action) -> str | None:
    """A Persian sentence if ``action`` cannot be used now (a skill still cooling down), else ``None``."""
    if action in SKILL_ACTIONS and not f.skills:
        return "این مهارت برای شما وجود ندارد."
    if action in (Action.SKILL, *SKILL_ACTIONS) and _status(f, "freeze"):
        return "❄️ یخ زده‌اید و این نوبت نمی‌توانید مهارت بزنید؛ حمله‌ی معمولی یا دفاع کنید."
    if f.skills and action in (Action.SKILL, *SKILL_ACTIONS):
        index = SKILL_ACTIONS.get(action, 2)
        if index < len(f.lock) and f.lock[index]:
            return f"این مهارت از سطح {fa(f.lock[index])} باز می‌شود."
        wait = f.skill_wait(index)
        if wait:
            name = f.skills[index]["name"]
            return f"مهارت «{name}» هنوز آماده نیست؛ {fa(wait)} نوبت دیگر صبر کنید یا مهارت دیگری بزنید."
    elif action is Action.SKILL and f.skill_ready_in > 1:
        return f"مهارت ویژه هنوز آماده نیست؛ {fa(f.skill_ready_in - 1)} نوبت دیگر صبر کنید یا حمله‌ی معمولی بزنید."
    return None


def _start_of_turn(me: Fighter, lines: list[str]) -> None:
    """Poison, burn and bleeding bite, gear heals, every counter moves one turn closer."""
    for s in [s for s in me.statuses if s["k"] in DOTS and s["t"] > 0]:
        me.hp = max(0, me.hp - int(s["v"]))
        icon, name = EFFECT_INFO[s["k"]]
        lines.append(f"{icon} {name} بودن از جان {me.name} {fa(int(s['v']))} کم کرد.")
        _fall(me, lines)
    if me.hp > 0 and (regen := _sum(me, "regen")):
        got = _heal(me, max(1, round(me.max_hp * regen)))
        if got:
            lines.append(f"💚 {me.name} {fa(got)} جان بازیافت.")
    for s in [s for s in me.statuses if s["k"] == "regen" and s["t"] > 0]:
        got = _heal(me, max(1, round(me.max_hp * s["v"])))
        if got:
            lines.append(f"💚 بازیابی {fa(got)} جان به {me.name} برگرداند.")
    for s in me.statuses:
        if s["k"] != "stun":  # a stun waits for the turn it takes away
            s["t"] -= 1
    me.statuses = [s for s in me.statuses if s["t"] > 0 or s["k"] == "stun"]
    me.cds = [max(0, c - 1) for c in me.cds]
    if me.skill_ready_in > 0:
        me.skill_ready_in -= 1


def _cast(me: Fighter, foe: Fighter, index: int, sk: HeroSkill, rng: random.Random, lines: list[str]) -> None:
    """A hero skill: its blows, then what it does besides."""
    me.cds[index] = sk.cd
    kinds = {e.k for e in sk.effects}
    if rng.random() < _dodge_chance(me, foe):
        lines.append(f"💨 {foe.name} چابک کنار پرید و از «{sk.name}» جاخالی داد!")
        return
    stat = eff_atk(me) if sk.kind == "phys" else eff_magic(me)
    power = sk.power * (1 + _sum(me, "skill_power"))
    total, crits, hits = 0, 0, 0
    for _ in range(sk.hits):
        if foe.hp <= 0:
            break
        damage, crit = _blow(me, foe, stat, sk.kind, rng, lines, pierce="pierce" in kinds, power=power,
                             force_crit="crit" in kinds, effects=sk.effects)
        total, crits, hits = total + damage, crits + crit, hits + 1
    many = f" ({fa(hits)} ضربه)" if hits > 1 else ""
    lines.append(
        f"{sk.emoji} {me.name} «{sk.name}» را آزاد کرد! {'🎯 ضربه‌ی کاری! ' if crits else ''}💥 {fa(total)} آسیب{many}"
    )
    for e in sk.effects:
        if e.c < 1 and rng.random() >= e.c:
            continue
        if e.k in HARMFUL:
            if foe.hp > 0:
                _inflict(me, foe, e.k, e.v, e.t, stat, lines, rng)
        elif e.k == "cleanse":
            gone = [s for s in me.statuses if s["k"] in HARMFUL]
            me.statuses = [s for s in me.statuses if s["k"] not in HARMFUL]
            if gone:
                lines.append(f"✨ {me.name} از اثرهای بد پاک شد.")
        elif e.k in ("atk_up", "def_up", "crit_up", "regen"):
            _apply(me, e.k, e.v, e.t)
            lines.append(f"{EFFECT_INFO[e.k][0]} {me.name} {EFFECT_INFO[e.k][1]} شد!")
        elif e.k == "lifesteal" and total:
            got = _heal(me, round(total * e.v))
            if got:
                lines.append(f"🩸 {me.name} {fa(got)} جان از دشمن ربود.")
        elif e.k == "heal":
            got = _heal(me, round(me.max_hp * e.v))
            if got:
                lines.append(f"💚 {me.name} {fa(got)} جان بازیافت.")
        elif e.k == "shield":
            me.shield = True
            lines.append(f"🛡️ {me.name} سپر گرفت.")
    _pet_strike(me, foe, rng, lines)
    _extra_hit(me, foe, rng, lines)
    if (c := _sum(me, "cd_cut")) and rng.random() < c:
        me.cds = [max(0, x - 1) for x in me.cds]
        lines.append(f"⏳ زمان برای {me.name} شتاب گرفت و مهارت‌ها زودتر برمی‌گردند.")


def act(battle: Battle, action: Action, rng: random.Random) -> list[str]:
    """Apply the current fighter's action; returns the log lines of this turn."""
    if battle.finished:
        raise ValueError("battle already finished")
    me, foe = battle.current, battle.other
    if action is not Action.SURRENDER and (problem := readiness_error(me, action)):
        raise ValueError(problem)
    lines: list[str] = []
    _start_of_turn(me, lines)

    if me.hp <= 0:
        battle.finished, battle.winner = True, 1 - battle.actor
        lines.append(f"🏆 {me.name} از پا افتاد و {foe.name} پیروز شد!")
        return lines

    stun = _status(me, "stun")
    if action is Action.SURRENDER:
        lines.append(f"🏳️ فرمانده {me.name} پرچم سفید را بالا برد و تسلیم شد!")
        battle.finished, battle.surrendered = True, True
        battle.winner = 1 - battle.actor
        return lines

    if stun:
        me.statuses.remove(stun)
        lines.append(f"💫 {me.name} گیج است و این نوبت را از دست داد!")
    elif action is Action.DEFEND:
        heal = max(1, me.max_hp // 20) + round(me.max_hp * _sum(me, "defend_heal"))
        got = _heal(me, heal)
        me.shield = True
        lines.append(f"🛡️ {me.name} سپر خود را بالا برد و {fa(got)} جان تازه گرفت.")
    else:
        picked = skill_of(me, action)
        use_legacy = action is Action.SKILL and picked is None
        if picked is not None:
            _cast(me, foe, picked[0], picked[1], rng, lines)
        elif use_legacy:
            if rng.random() < _dodge_chance(me, foe):
                lines.append(f"💨 {foe.name} چابک کنار پرید و از ضربه‌ی {me.name} جاخالی داد!")
                me.skill_ready_in = me.skill_cooldown
            else:
                stat = eff_atk(me) if me.skill_kind == "phys" else eff_magic(me)
                damage, crit = _blow(
                    me, foe, stat, me.skill_kind, rng, lines, pierce=me.skill_effect == "pierce",
                    force_crit=me.skill_effect == "crit", power=me.skill_power,
                )
                if me.skill_effect == "guard":
                    me.shield = True
                me.skill_ready_in = me.skill_cooldown
                lines.append(
                    f"{me.skill_emoji} {me.name} «{me.skill_name}» را آزاد کرد! "
                    f"{'🎯 ضربه‌ی کاری! ' if crit else ''}💥 {fa(damage)} آسیب"
                )
                _pet_strike(me, foe, rng, lines)
                _extra_hit(me, foe, rng, lines)
        elif rng.random() < _dodge_chance(me, foe):
            lines.append(f"💨 {foe.name} چابک کنار پرید و از ضربه‌ی {me.name} جاخالی داد!")
        else:
            offense = max(eff_atk(me), eff_magic(me) * 0.8)
            damage, crit = _blow(me, foe, offense, "phys", rng, lines,
                                 scale="magic" if eff_magic(me) * 0.8 > eff_atk(me) else "phys")
            lines.append(
                f"⚔️ {me.name} به {foe.name} حمله کرد! {'🎯 ضربه‌ی کاری! ' if crit else ''}💥 {fa(damage)} آسیب"
            )
            _pet_strike(me, foe, rng, lines)
            _extra_hit(me, foe, rng, lines)

    _fall(foe, lines)
    _fall(me, lines)
    if me.hp <= 0:  # thorns or poison finished the attacker
        battle.finished, battle.winner = True, 1 - battle.actor
        lines.append(f"🏆 {me.name} از پا افتاد و {foe.name} پیروز شد!")
        return lines
    if foe.hp <= 0:
        battle.finished = True
        battle.winner = battle.actor
        lines.append(f"🏆 {foe.name} بر زمین افتاد و {me.name} پیروز شد!")
        return lines

    battle.actor = 1 - battle.actor
    if battle.actor == 0:
        battle.round += 1
        if battle.round > battle.max_rounds:
            battle.finished = True
            a, b = battle.fighters
            battle.winner = None if a.hp_ratio == b.hp_ratio else (0 if a.hp_ratio > b.hp_ratio else 1)
            lines.append("⏳ ریگ‌های ساعت ریختند و نبرد به پایان رسید!")
    return lines


def auto_action(fighter: Fighter) -> Action:
    """Simple AI used for monsters, auto-played turns and auto-resolved hunts: the strongest skill that is ready."""
    if _status(fighter, "freeze"):
        return Action.ATTACK
    if fighter.has_skills:
        hurt = fighter.hp_ratio < 0.4
        for index in (2, 1, 0):
            if fighter.skill_wait(index) or (index < len(fighter.lock) and fighter.lock[index]):
                continue
            effects = {e["k"] for e in fighter.skills[index]["effects"]}
            if "heal" in effects and not hurt and fighter.hp_ratio > 0.8:
                continue
            return (Action.SKILL1, Action.SKILL2, Action.SKILL3)[index]
        return Action.ATTACK
    return Action.SKILL if fighter.skill_ready else Action.ATTACK


def auto_fight(battle: Battle, rng: random.Random) -> list[str]:
    """Play a battle to the end with the AI on both sides; returns the whole log."""
    log: list[str] = []
    while not battle.finished:
        log += act(battle, auto_action(battle.current), rng)
    return log


@dataclass
class Summary:
    rounds: int
    winner: int | None
    log: list[str] = field(default_factory=list)

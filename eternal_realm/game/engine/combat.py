"""Turn-based combat between two fighters (pure logic, serialisable, deterministic per RNG).

The same engine drives duels (humans pick actions) and hunts (the AI picks them).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from ...shared.text import fa
from ..data.classes import CharacterClass
from ..data.stats import Stats


class Action(StrEnum):
    ATTACK = "attack"
    SKILL = "skill"
    DEFEND = "defend"
    SURRENDER = "surrender"


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

    @property
    def hp_ratio(self) -> float:
        return self.hp / self.max_hp

    @property
    def skill_ready(self) -> bool:
        return self.skill_ready_in <= 0

    @classmethod
    def for_player(
        cls, player_id: int, name: str, char_class: CharacterClass, stats: Stats, mention: str = ""
    ) -> Fighter:
        skill = char_class.skill
        return cls(
            name=name, emoji=char_class.emoji, max_hp=stats.hp, hp=stats.hp, atk=stats.atk,
            defense=stats.defense, magic=stats.magic, speed=stats.speed, luck=stats.luck,
            skill_name=skill.name, skill_emoji=skill.emoji, skill_kind=skill.kind,
            skill_power=skill.power, skill_cooldown=skill.cooldown, skill_effect=skill.effect,
            crit_bonus=char_class.crit_bonus, player_id=player_id, mention=mention,
        )


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


def _dodge_chance(actor: Fighter, target: Fighter) -> float:
    return min(0.15, max(0.0, 0.03 + (target.speed - actor.speed) * 0.005))


def _crit_chance(actor: Fighter) -> float:
    return min(0.5, 0.05 + actor.luck * 0.003 + actor.crit_bonus)


def _strike(
    actor: Fighter, target: Fighter, offense: float, defense: float, rng: random.Random,
    *, force_crit: bool = False,
) -> tuple[int, bool]:
    raw = offense * rng.uniform(0.9, 1.1) - defense
    crit = force_crit or rng.random() < _crit_chance(actor)
    if crit:
        raw *= 1.5
    damage = max(1, round(raw))
    if target.shield:
        damage = max(1, damage // 2)
        target.shield = False
    return damage, crit


PET_CHANCE = 0.30


def _pet_strike(me: Fighter, foe: Fighter, rng: random.Random, lines: list[str]) -> None:
    """The attacker's pet may jump in with a small extra hit, announced at that very moment."""
    if not me.pet_power or foe.hp <= 0 or rng.random() >= PET_CHANCE:
        return
    damage = max(1, round(me.pet_power * rng.uniform(0.9, 1.1) - foe.defense * 0.25))
    foe.hp = max(0, foe.hp - damage)
    lines.append(f"{me.pet_emoji} {me.pet_name} همراه {me.name} هم به {foe.name} حمله کرد! 💥 {fa(damage)} آسیب")


def act(battle: Battle, action: Action, rng: random.Random) -> list[str]:
    """Apply the current fighter's action; returns the log lines of this turn."""
    if battle.finished:
        raise ValueError("battle already finished")
    me, foe = battle.current, battle.other
    lines: list[str] = []
    if me.skill_ready_in > 0:
        me.skill_ready_in -= 1

    if action is Action.SURRENDER:
        lines.append(f"🏳️ فرمانده {me.name} پرچم سفید را بالا برد و تسلیم شد!")
        battle.finished, battle.surrendered = True, True
        battle.winner = 1 - battle.actor
        return lines

    if action is Action.DEFEND:
        heal = max(1, me.max_hp // 20)
        me.hp = min(me.max_hp, me.hp + heal)
        me.shield = True
        lines.append(f"🛡️ {me.name} سپر خود را بالا برد و {fa(heal)} جان تازه گرفت.")
    else:
        use_skill = action is Action.SKILL
        if use_skill and not me.skill_ready:
            raise ValueError("skill is on cooldown")
        if rng.random() < _dodge_chance(me, foe):
            lines.append(f"💨 {foe.name} چابک کنار پرید و از ضربه‌ی {me.name} جاخالی داد!")
            if use_skill:
                me.skill_ready_in = me.skill_cooldown
        elif use_skill:
            stat = me.atk if me.skill_kind == "phys" else me.magic
            piercing = me.skill_effect == "pierce"
            armor = 0.0 if piercing else foe.defense * (0.5 if me.skill_kind == "phys" else 0.3)
            damage, crit = _strike(me, foe, stat * me.skill_power, armor, rng, force_crit=me.skill_effect == "crit")
            foe.hp = max(0, foe.hp - damage)
            if me.skill_effect == "guard":
                me.shield = True
            me.skill_ready_in = me.skill_cooldown
            lines.append(
                f"{me.skill_emoji} {me.name} «{me.skill_name}» را آزاد کرد! "
                f"{'🎯 ضربه‌ی کاری! ' if crit else ''}💥 {fa(damage)} آسیب"
            )
            _pet_strike(me, foe, rng, lines)
        else:
            offense = max(me.atk, me.magic * 0.8)
            damage, crit = _strike(me, foe, offense, foe.defense * 0.5, rng)
            foe.hp = max(0, foe.hp - damage)
            lines.append(
                f"⚔️ {me.name} به {foe.name} حمله کرد! {'🎯 ضربه‌ی کاری! ' if crit else ''}💥 {fa(damage)} آسیب"
            )
            _pet_strike(me, foe, rng, lines)

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
    """Simple AI used for monsters and for auto-resolved hunts."""
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

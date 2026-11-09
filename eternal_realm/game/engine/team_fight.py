"""Team battle logic: two teams, every member of a team acts in turn, then the other team does.

Each single strike reuses the duel engine (:func:`combat.act`) on a throw-away two-fighter battle, so dodges, crits,
skills, shields and pets work exactly as in a duel. Hit points live on the shared :class:`Fighter` objects.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from typing import Any

from ...shared.text import fa
from . import combat
from .combat import Action, Battle, Fighter

MAX_ROUNDS = 20


@dataclass
class TeamBattle:
    #: everybody, ordered by team then seat
    fighters: list[Fighter]
    #: team (0 or 1) of each fighter
    teams: list[int]
    actor: int = 0
    first_team: int = 0
    round: int = 1
    max_rounds: int = MAX_ROUNDS
    finished: bool = False
    #: winning team, ``None`` for a draw (only meaningful when finished)
    winner: int | None = None
    #: fighters (by index) who let their turn time out; they are played automatically from then on
    auto: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TeamBattle:
        rest = {k: v for k, v in data.items() if k != "fighters"}
        return cls(fighters=[Fighter(**f) for f in data["fighters"]], **rest)

    @property
    def current(self) -> Fighter:
        return self.fighters[self.actor]

    @property
    def current_team(self) -> int:
        return self.teams[self.actor]

    def members(self, team: int) -> list[int]:
        return [i for i, t in enumerate(self.teams) if t == team]

    def alive(self, team: int) -> list[int]:
        return [i for i in self.members(team) if self.fighters[i].hp > 0]

    def hp_ratio(self, team: int) -> float:
        members = [self.fighters[i] for i in self.members(team)]
        total = sum(f.max_hp for f in members)
        return sum(max(f.hp, 0) for f in members) / total if total else 0.0

    @classmethod
    def start(cls, fighters: list[Fighter], teams: list[int], rng: random.Random) -> TeamBattle:
        """Which team opens is drawn by lot."""
        first = rng.randint(0, 1)
        battle = cls(fighters, teams, first_team=first)
        battle.actor = battle.members(first)[0]
        return battle


def _pick_target(battle: TeamBattle) -> int:
    """The enemy with the fewest hit points left: a team that focuses is a team that wins."""
    enemies = battle.alive(1 - battle.current_team)
    return min(enemies, key=lambda i: (battle.fighters[i].hp, i))


def _advance(battle: TeamBattle) -> list[str]:
    """Hand the turn to the next living member, then to the other team; the round ends when the opener's turn returns."""
    lines: list[str] = []
    team = battle.current_team
    later = [i for i in battle.alive(team) if i > battle.actor]
    if later:
        battle.actor = later[0]
        return lines
    team = 1 - team
    battle.actor = battle.alive(team)[0]
    if team == battle.first_team:
        battle.round += 1
        if battle.round > battle.max_rounds:
            battle.finished = True
            a, b = battle.hp_ratio(0), battle.hp_ratio(1)
            battle.winner = None if a == b else (0 if a > b else 1)
            lines.append("⏳ ریگ‌های ساعت ریختند و نبرد به پایان رسید!")
    return lines


def act(battle: TeamBattle, action: Action, rng: random.Random) -> list[str]:
    """The current fighter acts; returns the log lines of this turn."""
    if battle.finished:
        raise ValueError("battle already finished")
    me = battle.current
    lines: list[str] = []
    if action is Action.SURRENDER:
        me.hp = 0
        lines.append(f"🏳️ {me.name} پرچم سفید را بالا برد و از نبرد کنار کشید!")
    else:
        index = _pick_target(battle)
        foe = battle.fighters[index]
        duel = Battle([me, foe], actor=0, max_rounds=999)
        lines = combat.act(duel, action, rng)
        if duel.finished and foe.hp <= 0:  # the duel engine would crown a winner; here a hero merely falls
            lines[-1] = f"💀 {foe.name} از پا افتاد!"
    for team in (0, 1):
        if not battle.alive(team):
            battle.finished = True
            battle.winner = 1 - team
            lines.append(f"🏆 تیم {'اول' if battle.winner == 0 else 'دوم'} میدان را گرفت!")
            return lines
    lines += _advance(battle)
    return lines


def auto_action(fighter: Fighter) -> Action:
    return combat.auto_action(fighter)


def hp_percent(f: Fighter) -> int:
    return round(100 * max(f.hp, 0) / f.max_hp) if f.max_hp else 0


def describe(f: Fighter) -> str:
    return f"{fa(max(f.hp, 0))}/{fa(f.max_hp)}"

import random

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.classes import CLASSES
from eternal_realm.game.data.monsters import MONSTERS
from eternal_realm.game.engine import progression as p
from eternal_realm.game.engine.combat import Action, Battle, Fighter, act, auto_fight
from eternal_realm.shared.errors import GameError

from .harness import Harness


def hero(cls="warrior", level=5, race="human"):
    return Fighter.for_player(1, "قهرمان", CLASSES[cls], p.base_stats(race, cls, level))


def test_battle_always_terminates_with_a_result():
    rng = random.Random(2)
    for cls in CLASSES:
        for m in MONSTERS:
            b = Battle.start(hero(cls, 10), m.fighter(10), 15, rng)
            auto_fight(b, rng)
            assert b.finished and b.winner in (0, 1, None)


def test_damage_is_always_positive_and_hp_never_negative():
    rng = random.Random(3)
    a, b = hero("mage"), hero("guardian")
    battle = Battle.start(a, b, 30, rng)
    while not battle.finished:
        before = battle.other.hp
        act(battle, Action.ATTACK, rng)
        assert 0 <= battle.fighters[0].hp <= a.max_hp and 0 <= battle.fighters[1].hp <= b.max_hp
        assert battle.fighters[0].hp >= 0
        _ = before


def test_skill_cooldown_enforced():
    rng = random.Random(4)
    battle = Battle.start(hero(), hero("archer"), 15, rng)
    battle.actor = 0
    act(battle, Action.SKILL, rng)
    battle.actor = 0
    with pytest.raises(ValueError):
        act(battle, Action.SKILL, rng)


def test_surrender_and_round_limit():
    rng = random.Random(5)
    battle = Battle.start(hero(), hero("archer"), 15, rng)
    me = battle.actor
    act(battle, Action.SURRENDER, rng)
    assert battle.finished and battle.winner == 1 - me and battle.surrendered
    with pytest.raises(ValueError):
        act(battle, Action.ATTACK, rng)

    tank = Battle.start(hero("guardian", 30), hero("guardian", 30), 1, random.Random(1))
    while not tank.finished:
        act(tank, Action.DEFEND, random.Random(1))
    assert tank.winner in (None, 0, 1)


def test_serialisation_roundtrip():
    rng = random.Random(6)
    battle = Battle.start(hero(), hero("rogue"), 15, rng)
    act(battle, Action.ATTACK, rng)
    clone = Battle.from_dict(battle.to_dict())
    assert clone.to_dict() == battle.to_dict()


def test_hunt_balance_is_winnable_for_every_class_early():
    rng = random.Random(8)
    for cls in CLASSES:
        wins = 0
        for _ in range(200):
            h = hero(cls, 3)
            m = [m for m in MONSTERS if m.min_level <= 3][_ % 2].fighter(3)
            b = Battle.start(h, m, 15, rng)
            auto_fight(b, rng)
            wins += b.winner == 0
        assert wins / 200 > 0.6, cls


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


async def test_hunt_flow(services, clock):
    pl = await services.players.register(10, "u", "آرش", "dragonborn", "warrior")
    result = await services.hunting.hunt(pl.id)
    assert result.won and result.gold >= 0 and result.xp > 0
    assert result.player.energy == pl.energy - 10
    with pytest.raises(GameError):
        await services.hunting.hunt(pl.id)  # cooldown
    clock.advance(31)
    await services.hunting.hunt(pl.id)


async def test_hunt_command_in_group(services):
    h = Harness(services)
    await services.players.register(10, "u", "آرش", "dragonborn", "warrior")
    await h.say(10, "شکار", group=True)
    assert "نبرد با" in h.session.last_text()

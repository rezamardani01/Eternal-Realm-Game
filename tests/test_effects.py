import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.effects import EFFECTS, get_effect
from eternal_realm.game.data.stats import Stats
from eternal_realm.game.services.effects import ALTAR_PRICE
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, gold=5_000):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


def test_effects_change_stats_in_the_stated_way():
    base = Stats(hp=100, atk=100, defense=100, magic=100, speed=100, luck=20)
    blood = get_effect("blood").apply(base)
    assert blood.atk == 120 and blood.defense == 85  # a curse that trades defence for attack
    assert get_effect("shadow").apply(base).luck == 15
    assert get_effect("sun").apply(base).hp == 110
    assert all(e.lines() for e in EFFECTS) and any(not e.blessing for e in EFFECTS)
    assert get_effect("shadow").apply(Stats(luck=3)).luck == 0  # never below zero


async def test_an_active_effect_changes_the_hero_and_then_expires(services, db, clock):
    p = await hero(services, db, 1, "آرش")
    before = await services.characters.stats(p)
    async with db.transaction() as tx:
        await services.effects.give(tx, p.id, get_effect("blood"))
    during = await services.characters.stats(p)
    assert during.atk > before.atk and during.defense < before.defense
    assert [e.id for e, _ in await services.effects.active(p.id)] == ["blood"]
    clock.advance(61 * 60)
    assert await services.effects.active(p.id) == []
    assert await services.characters.stats(p) == before


async def test_praying_costs_gold_and_grants_something(services, db):
    p = await hero(services, db, 2, "سارا")
    gold = p.gold
    effect = await services.effects.pray(p)
    assert (await services.players.require(2)).gold == gold - ALTAR_PRICE
    assert [e.id for e, _ in await services.effects.active(p.id)] == [effect.id]
    poor = await hero(services, db, 3, "فقیر", gold=0)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET gold = 0 WHERE id = ?", (poor.id,))
    with pytest.raises(GameError):
        await services.effects.pray(await services.players.require(3))


async def test_blessings_are_the_common_outcome(services):
    good = sum(services.effects.roll().blessing for _ in range(400))
    assert 240 < good < 330  # about 70%


async def test_cleansing_only_removes_curses(services, db):
    p = await hero(services, db, 4, "رها")
    with pytest.raises(GameError, match="نفرینی"):
        await services.effects.cleanse(p)
    async with db.transaction() as tx:
        await services.effects.give(tx, p.id, get_effect("slow"))
        await services.effects.give(tx, p.id, get_effect("sun"))
    assert await services.effects.cleanse(p) == 1
    assert [e.id for e, _ in await services.effects.active(p.id)] == ["sun"]


async def test_glass_flow(h, services, db):
    p = await hero(services, db, 5, "نگار")
    await h.say(5, "محراب", group=True)
    assert "محراب" in h.session.last_text()
    await h.tap(5, "دعا", group=True)
    assert "تأیید دعا" in h.session.sent("editMessageText")[-1]["text"]
    await h.tap(5, "بله، دعا کن", group=True)
    assert await services.effects.active(p.id)

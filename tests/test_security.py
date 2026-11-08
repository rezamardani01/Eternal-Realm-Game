"""Races and abuse: fast double taps, parallel buyers, a stuck database lock."""

import asyncio

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db import database
from eternal_realm.db.repos import season as season_repo
from eternal_realm.db.repos import wallet

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, gold=0, level=5):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def test_rapid_double_tap_on_a_claim_pays_once(h, services, db):
    p = await hero(services, db, 1, "آرش")
    async with db.transaction() as tx:
        for _ in range(4):
            await season_repo.add_points(tx, p.id, "boss", services.ctx.now())
    before = (await services.players.require(1)).gold
    await h.panel(1, "pathtiers", "1")
    data = h.session.last_markup_rows()[1][0]["callback_data"]
    await asyncio.gather(*(h.click(1, data) for _ in range(6)))
    gold = (await services.players.require(1)).gold
    from eternal_realm.game.data.season import reward_for

    assert gold == before + reward_for("free", 1).gold


async def test_parallel_transfers_cannot_overdraw_a_wallet(services, db):
    a, b = await hero(services, db, 20, "آرش", gold=1_000), await hero(services, db, 21, "سارا")
    me = await services.players.require(20)
    results = await asyncio.gather(
        *(services.economy.transfer(me, b, 400) for _ in range(5)), return_exceptions=True
    )
    paid = sum(not isinstance(r, Exception) for r in results)
    mine = (await services.players.require(20)).gold
    assert mine >= 0 and mine == a.gold - paid * 400 and paid == a.gold // 400
    assert (await services.players.require(21)).gold == b.gold + paid * 400


async def test_one_player_is_handled_one_update_at_a_time(h, services, db):
    from eternal_realm.bot.middlewares import UserLockMiddleware

    lock = UserLockMiddleware()
    order = []

    async def slow(event, data):
        order.append(("start", event.from_user.id))
        await asyncio.sleep(0.01)
        order.append(("end", event.from_user.id))

    class Event:
        def __init__(self, uid):
            self.from_user = type("U", (), {"id": uid})()

    await asyncio.gather(lock(slow, Event(1), {}), lock(slow, Event(1), {}), lock(slow, Event(2), {}))
    ones = [x for x in order if x[1] == 1]
    assert ones == [("start", 1), ("end", 1), ("start", 1), ("end", 1)]  # never interleaved
    assert not lock._locks and not lock._waiting  # nothing leaks


async def test_a_stuck_database_lock_becomes_an_error_not_a_hang(db, monkeypatch):
    monkeypatch.setattr(database, "LOCK_TIMEOUT", 0.05)
    async with db.transaction():
        with pytest.raises(RuntimeError, match="lock timeout"):
            async with db.read():
                pass
    async with db.read():  # and the lock is healthy again afterwards
        pass

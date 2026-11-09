import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.services.dungeon import COOLDOWN, ENERGY_COST, ROOMS
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=10):
    p = await services.players.register(uid, f"u{uid}", name, "dragonborn", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ?, energy = 100, energy_at = ? WHERE id = ?",
                         (level, services.ctx.now(), p.id))
        await wallet.apply(tx, p.id, gold=1_000, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def test_a_full_run_ends_in_win_or_defeat_and_pays_once(services, db):
    p = await hero(services, db, 2, "آرش", level=30)
    run = await services.dungeon.enter(p)
    assert run.stage == 0 and (await services.dungeon.current(p.id)) is not None
    assert (await services.players.require(2)).energy <= 100 - ENERGY_COST + 1
    gold = (await services.players.require(2)).gold
    view = None
    for _ in range(ROOMS):
        view = await services.dungeon.advance(p)
        if view.status != "active":
            break
    assert view.status in ("won", "dead") and view.stage <= ROOMS
    assert await services.dungeon.current(p.id) is None
    assert (await services.players.require(2)).gold == gold + view.paid_gold
    with pytest.raises(GameError, match="نیستید"):
        await services.dungeon.advance(p)


async def test_cannot_enter_twice_or_before_the_cooldown(services, db, clock):
    p = await hero(services, db, 2, "سارا")
    await services.dungeon.enter(p)
    with pytest.raises(GameError, match="همین حالا"):
        await services.dungeon.enter(p)
    await services.dungeon.leave(p)
    with pytest.raises(GameError, match="بسته"):
        await services.dungeon.enter(p)
    clock.advance(COOLDOWN + 1)
    await services.dungeon.enter(p)


async def test_not_enough_energy_blocks_entry(services, db):
    p = await hero(services, db, 3, "رها")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 5 WHERE id = ?", (p.id,))
    with pytest.raises(GameError, match="انرژی"):
        await services.dungeon.enter(await services.players.require(3))


async def test_glass_flow_walks_the_whole_dungeon(h, services, db):
    await hero(services, db, 4, "نگار", level=40)
    await h.say(4, "سیاه‌چال")
    await h.tap(4, "ورود به سیاه‌چال")
    assert "تأیید ورود" in h.session.sent("editMessageText")[-1]["text"]
    await h.tap(4, "بله، وارد شو")
    for _ in range(ROOMS):
        if not any("اتاق بعدی" in label for label in h.labels()):
            break
        await h.tap(4, "اتاق بعدی")
    text = h.session.sent("editMessageText")[-1]["text"]
    assert "سیاه‌چال را فتح کردید" in text or "جانتان تمام شد" in text
    assert await services.dungeon.current((await services.players.require(4)).id) is None

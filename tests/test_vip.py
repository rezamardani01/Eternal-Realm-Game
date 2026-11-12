import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import season as season_repo
from eternal_realm.game.data.packs import PACKS

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=10):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ?, energy = 100, energy_at = ? WHERE id = ?",
                         (level, services.ctx.now(), p.id))
    return await services.players.require(uid)


async def buy(services, p, pack_id="vip_30"):
    order = await services.payments.create_order(p, pack_id)
    await services.payments.complete(p.platform_user_id, order.payload, order.amount, f"c-{order.id}")


def test_vip_pack_is_cheap_and_gives_no_combat_stats():
    pack = PACKS["vip_30"]
    assert pack.vip_days == 30 and pack.price_toman == 25_900 and not pack.items


async def test_buying_vip_sets_and_extends_the_end_date(services, db, clock):
    p = await hero(services, db, 1, "آرش")
    now = services.ctx.now()
    await buy(services, p)
    first = (await services.players.require(1)).vip_until
    assert first == now + 30 * 86400
    await buy(services, await services.players.require(1))  # renewing adds to what is left
    assert (await services.players.require(1)).vip_until == first + 30 * 86400
    clock.advance(100 * 86400)
    await buy(services, await services.players.require(1))  # an expired one restarts from now
    assert (await services.players.require(1)).vip_until == services.ctx.now() + 30 * 86400


async def test_vip_shortens_cooldowns_adds_a_mission_and_path_points(services, db):
    free, vip = await hero(services, db, 2, "رایگان"), await hero(services, db, 3, "ویژه")
    await buy(services, vip)
    a = await services.activities.perform(free.id, "fishing")
    b = await services.activities.perform(vip.id, "fishing")
    assert b.next_in == round(a.next_in * 0.8)
    assert len(await services.missions.today(free)) == 3
    assert len(await services.missions.today(await services.players.require(3))) == 4
    async with db.transaction() as tx:
        await season_repo.add_points(tx, free.id, "boss", services.ctx.now())
        await season_repo.add_points(tx, vip.id, "boss", services.ctx.now())
    assert (await services.season.state(free)).points - 5 == 30
    assert (await services.season.state(vip)).points - round(5 * 1.1) == 33


async def test_vip_page_and_badge(h, services, db):
    p = await hero(services, db, 4, "نگار")
    await h.say(4, "قلمرو", group=True)
    await h.panel(4, "vip", group=True)
    assert "غیرفعال" in h.session.last_text()
    await buy(services, p)
    await h.panel(4, "vip", group=True)
    assert "وضعیت: فعال" in h.session.last_text()
    await h.panel(4, "profile", group=True)
    assert "VIP" in h.session.last_text()

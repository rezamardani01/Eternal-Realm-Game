import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import clans as clan_repo
from eternal_realm.db.repos import season as season_repo
from eternal_realm.db.repos import wallet
from eternal_realm.game.data import wheel as wheel_data
from eternal_realm.game.data.achievements import FAMILIES
from eternal_realm.game.data.pets import PETS
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999, provider_token="W-T"), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, uid, name, level=5):
    return await services.players.register(uid, f"u{uid}", name, "elf", "archer")


def test_the_free_wheel_never_comes_up_empty_and_pays_modestly():
    assert not any(s.empty for s in wheel_data.FREE_SLICES)
    assert max(s.gold for s in wheel_data.FREE_SLICES) <= 8_000 and max(s.crystal for s in wheel_data.FREE_SLICES) <= 10


async def test_the_daily_free_spin_comes_back_every_day(h, services, clock):
    p = await hero(services, 1, "آرش")
    assert await services.wheel.free_ready(p.id)
    await h.panel(1, "wheel")
    assert any("چرخش رایگان امروز" in x for x in h.labels())
    await h.panel(1, "wheelspin", "free")
    assert "گردونه شانس" in h.session.last_text() and "فردا دوباره" in h.session.last_text()
    async with services.ctx.db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM wheel_log WHERE player_id = ?", (p.id,), 0) == 1  # a prize was paid
    assert not await services.wheel.free_ready(p.id)
    with pytest.raises(GameError, match="فردا"):
        await services.wheel.spin(p, free=True)
    await h.panel(1, "wheel")
    assert not any("چرخش رایگان امروز" in x for x in h.labels())
    clock.advance(86400)
    assert await services.wheel.free_ready(p.id)


async def test_a_full_week_of_daily_rewards_pays_crystals(services, db, clock):
    p = await hero(services, 1, "آرش")
    crystals = p.crystal
    got = []
    for _ in range(7):
        reward = await services.players.claim_daily(p.id)
        got.append(reward.crystal)
        clock.advance(86400)
    assert got == [0, 0, 0, 0, 0, 0, 3]
    assert (await services.players.require(1)).crystal == crystals + 3


async def test_finishing_all_the_days_missions_pays_two_crystals(services, db):
    p = await hero(services, 1, "آرش")
    views = await services.missions.today(p)
    async with db.transaction() as tx:
        await tx.execute("UPDATE daily_missions SET progress = target WHERE player_id = ?", (p.id,))
    crystals = (await services.players.require(1)).crystal
    done = [await services.missions.claim(p, m.slot) for m in views]
    assert [m.bonus_crystal for m in done] == [0] * (len(views) - 1) + [2]
    assert (await services.players.require(1)).crystal == crystals + 2


async def test_clan_war_prizes_include_crystals_and_a_boost(services, db, clock):
    a, b = await hero(services, 1, "رهبر‌جان"), await hero(services, 2, "آرش‌جان")
    async with db.transaction() as tx:
        await wallet.apply(tx, a.id, gold=5_000, reason="t", now=services.ctx.now())
    clan = await services.clans.create(await services.players.require(1), "جنگجویان")
    await services.clans.join(b, clan.id)
    clock.advance(clan_repo.WEEK)
    async with db.transaction() as tx:
        await clan_repo.add_war_points(tx, a.id, 50, services.ctx.now())
    clock.advance(clan_repo.WEEK)
    before = await services.players.require(2)
    await services.clans.claim_war(b)
    after = await services.players.require(2)
    assert after.crystal == before.crystal + 10 and after.boost_until >= services.ctx.now() + 24 * 3600 - 5


async def test_every_friend_brought_in_adds_half_a_day_of_boost(h, services):
    inviter = await hero(services, 5, "دعوت‌کننده")
    await h.say(20, "/start ref_5")
    await h.say(20, "سارا‌جان")
    await h.click(20, h.button_data("الف"))
    await h.click(20, h.button_data("کماندار"))
    me = await services.players.require(5)
    assert me.boost_until >= services.ctx.now() + 12 * 3600 - 5 and inviter.boost_until == 0
    newcomer = await services.players.find(20)
    assert newcomer is not None and newcomer.boost_until >= services.ctx.now() + 3 * 86400 - 5  # the welcome gift


async def test_every_pet_the_treasury_sells_can_be_earned_for_free(services, db):
    sold = {p.id for p in PETS if p.pack_id}
    free = {s.pet for f in FAMILIES for s in f.steps if s.pet}
    assert sold <= free
    p = await hero(services, 1, "آرش")
    async with db.transaction() as tx:
        for _ in range(50):
            await season_repo.add_points(tx, p.id, "boss_win", services.ctx.now())
    for _ in range(3):
        await services.achievements.claim(p, "bossbane")
    async with db.read() as tx:
        assert await tx.scalar("SELECT 1 FROM player_pets WHERE player_id = ? AND pet_id = 'dragon'", (p.id,), 0)


async def test_city_bundles_are_limited_per_week(services, db, clock):
    from eternal_realm.game.data import city as d

    p = await hero(services, 1, "آرش")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=100_000, reason="t", now=services.ctx.now())
        await tx.execute("UPDATE players SET level = 10 WHERE id = ?", (p.id,))
    await services.city.found(await services.players.require(1), "آذرگان", d.FLAGS[0][0])
    for n in range(8):
        order = await services.payments.create_order(await services.players.require(1), "city_food")
        await services.payments.complete(1, order.payload, order.amount, f"c{n}")
    await services.payments.create_order(await services.players.require(1), "city_food")

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import season as repo
from eternal_realm.game.data.packs import PACKS
from eternal_realm.game.data.season import (
    POINTS_PER_TIER, SEASON_SECONDS, TIERS, reward_for, season_of,
)
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name):
    return await services.players.register(uid, f"u{uid}", name, "elf", "warrior")


async def add(db, services, player, deed, times=1):
    async with db.transaction() as tx:
        for _ in range(times):
            await repo.add_points(tx, player.id, deed, services.ctx.now())


def test_the_ticket_costs_49900_toman_and_the_path_has_100_tiers():
    assert PACKS["season_ticket"].price_toman == 49_900 and TIERS == 100
    assert any(reward_for("free", t) for t in range(1, TIERS + 1))
    assert reward_for("ticket", 100).title == "اسطوره‌ی فصل" and reward_for("ticket", 5).crystal == 5
    assert all(reward_for("ticket", t) for t in range(1, TIERS + 1))


async def test_points_become_tiers_and_rewards_pay_once(services, db):
    p = await hero(services, db, 1, "آرش")
    with pytest.raises(GameError, match="نرسیده"):
        await services.season.claim(p, "free", 1)
    await add(db, services, p, "boss", 4)  # 4 x 30 = 120 points = tier 1
    st = await services.season.state(p)
    assert st.tier == 1 and ("free", 1) in st.available()
    gold = (await services.players.require(1)).gold
    reward = await services.season.claim(p, "free", 1)
    assert (await services.players.require(1)).gold == gold + reward.gold
    with pytest.raises(GameError, match="قبلاً"):
        await services.season.claim(p, "free", 1)
    with pytest.raises(GameError, match="بلیط"):
        await services.season.claim(p, "ticket", 1)


async def test_ticket_unlocks_the_second_track_and_claim_all(services, db):
    p = await hero(services, db, 2, "سارا")
    async with db.transaction() as tx:
        assert await repo.grant_ticket(tx, p.id, services.ctx.now()) is True
        assert await repo.grant_ticket(tx, p.id, services.ctx.now()) is False
    await add(db, services, p, "boss", 17)  # 510 points = tier 5
    before = await services.players.require(2)
    done = await services.season.claim_all(p)
    after = await services.players.require(2)
    assert {t for t, _, _ in done} == {"free", "ticket"} and after.crystal >= before.crystal + 5
    with pytest.raises(GameError):
        await services.season.claim_all(p)


async def test_a_new_season_starts_from_zero(services, db, clock):
    p = await hero(services, db, 3, "رها")
    await add(db, services, p, "boss", 4)
    assert (await services.season.state(p)).tier == 1
    clock.advance(SEASON_SECONDS)
    assert (await services.season.state(p)).points == 0
    assert season_of(services.ctx.now()) > 0


async def test_real_play_earns_points(services, db):
    p = await hero(services, db, 4, "نگار")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 100, energy_at = ? WHERE id = ?", (services.ctx.now(), p.id))
    await services.activities.perform(p.id, "fishing")
    await services.players.claim_daily(p.id)
    assert (await services.season.state(p)).points == 5 + 10


async def test_ticket_order_unlocks_and_blocks_a_repeat(services, db):
    p = await hero(services, db, 5, "پویا")
    order = await services.payments.create_order(p, "season_ticket")
    await services.payments.complete(5, order.payload, order.amount, "charge-9")
    assert (await services.season.state(p)).premium
    with pytest.raises(GameError, match="از قبل"):
        await services.payments.create_order(p, "season_ticket")


async def test_glass_flow(h, services, db):
    p = await hero(services, db, 6, "مینا")
    await add(db, services, p, "boss", 4)
    await h.say(6, "قلمرو", group=True)
    await h.tap(6, "قهرمان من", group=True)
    await h.tap(6, "مسیر قهرمانی", group=True)
    text = h.session.sent("editMessageText")[-1]["text"]
    assert "مرحله‌ی شما" in text and "جایزه‌ی رایگان بعدی" in text
    await h.tap(6, "دریافت همه", group=True)
    assert (await services.season.state(p)).claimed
    await h.tap(6, "مراحل و جایزه‌ها", group=True)
    assert "مراحل مسیر قهرمانی" in h.session.sent("editMessageText")[-1]["text"]
    assert POINTS_PER_TIER == 100

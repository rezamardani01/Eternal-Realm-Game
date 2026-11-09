import pytest

from eternal_realm.bot import notifier
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import season as season_repo
from eternal_realm.db.repos import wallet
from eternal_realm.game.data import city as d
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, uid, name):
    return await services.players.register(uid, f"u{uid}", name, "elf", "archer")


def dms(h, chat):
    return [p for n, p in h.session.calls if n == "sendMessage" and p.get("chat_id") == chat]


async def test_an_achievement_that_opens_is_announced_once_with_a_claim_button(h, services, db):
    p = await hero(services, 1, "آرش")
    async with db.transaction() as tx:
        for _ in range(10):
            await season_repo.add_points(tx, p.id, "hunt", services.ctx.now())
    assert await notifier.deliver(h.bot, services) == 1
    message = dms(h, 1)[-1]
    assert "دستاورد باز شد" in message["text"] and "شکارچی" in message["text"] and "۱۰ بار" in message["text"]
    button = message["reply_markup"]["inline_keyboard"][0][0]
    assert "دریافت پاداش" in button["text"] and button["callback_data"].startswith("p:achf:hunt")
    assert await notifier.deliver(h.bot, services) == 0  # nothing is sent twice
    async with db.transaction() as tx:  # one more deed does not repeat the news
        await season_repo.add_points(tx, p.id, "hunt", services.ctx.now())
    assert await notifier.deliver(h.bot, services) == 0
    await h.click(1, button["callback_data"])
    assert "دریافت پاداش" in " ".join(h.labels())


async def test_levels_streaks_pets_and_friends_open_achievements_too(h, services, db, clock):
    p = await hero(services, 1, "آرش")
    async with db.transaction() as tx:
        await services.players.grant_xp(tx, p.id, 10**7)
    await notifier.deliver(h.bot, services)
    assert any("قهرمان" in m["text"] and "دستاورد باز شد" in m["text"] for m in dms(h, 1))
    h.session.reset()
    for _ in range(7):
        await services.players.claim_daily(p.id)
        clock.advance(86400)
    async with db.transaction() as tx:
        await services.pets.grant(tx, p.id, "fox")
    await notifier.deliver(h.bot, services)
    texts = " ".join(m["text"] for m in dms(h, 1))
    assert "پشتکار" in texts and "دوستدار حیوان" in texts


async def test_a_sold_listing_and_an_ended_boost_reach_their_owners(h, services, db, clock):
    seller, buyer = await hero(services, 1, "فروشنده"), await hero(services, 2, "خریدار")
    async with db.transaction() as tx:
        await services.inventory.grant(tx, seller.id, "iron_ore", 5)
        await wallet.apply(tx, buyer.id, gold=5_000, reason="t", now=services.ctx.now())
    from eternal_realm.game.data.items import get_item

    listing = await services.market.list_stack(await services.players.require(1), get_item("iron_ore"), 5, 400)
    await services.market.buy(await services.players.require(2), listing.id)
    await notifier.deliver(h.bot, services)
    assert any("آگهی شما فروخته شد" in m["text"] and "سنگ آهن" in m["text"] for m in dms(h, 1))
    assert not dms(h, 2)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET boost_until = ? WHERE id = ?", (services.ctx.now() + 3600, buyer.id))
    await notifier.deliver(h.bot, services)
    assert not any("تمام شد" in m["text"] for m in dms(h, 2))
    clock.advance(3700)
    await notifier.deliver(h.bot, services)
    assert any("بوست دو برابر شما تمام شد" in m["text"] for m in dms(h, 2))
    h.session.reset()
    await notifier.deliver(h.bot, services)
    assert not dms(h, 2)


async def city(services, db, uid, name, city_name="آذرگان"):
    p = await hero(services, uid, name)
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=50_000, reason="t", now=services.ctx.now())
        await tx.execute("UPDATE players SET level = 10 WHERE id = ?", (p.id,))
    return await services.players.require(uid), await services.city.found(await services.players.require(uid), city_name, d.FLAGS[0][0])


async def test_the_city_treasury_pays_out_with_a_fee_and_a_daily_limit(h, services, db, clock):
    p, c = await city(services, db, 7, "فرمانروا")
    async with db.transaction() as tx:
        await tx.execute("UPDATE cities SET gold = 100000 WHERE id = ?", (c.id,))
    await h.panel(7, "city")
    assert "🏛️ خزانه شهر" in h.labels()
    await h.panel(7, "citytreas")
    assert "برداشت از خزانه" in " ".join(h.labels()) and "واریز سکه" in " ".join(h.labels())
    await h.panel(7, "citywd")
    assert any("۱٬۰۰۰" in x for x in h.labels())
    await h.panel(7, "citywdq", "10000")
    assert "تأیید برداشت" in h.session.last_text() and "کارمزد" in h.session.last_text()
    before = (await services.players.require(7)).gold
    await h.panel(7, "citywdok", "10000")
    assert (await services.players.require(7)).gold == before + 8_000  # 20% fee
    assert (await services.city.mine(p)).res["gold"] < 100_000 - 10_000 + 600
    await services.city.withdraw(p, 20_000)
    with pytest.raises(GameError, match="سقف"):
        await services.city.withdraw(p, 5_000)  # 30,000 a day is the limit
    with pytest.raises(GameError, match="۱۰۰"):
        await services.city.withdraw(p, 50)
    clock.advance(86400)
    await services.city.withdraw(p, 5_000)
    poor, pc = await city(services, db, 8, "فقیرشهر", "فقیرآباد")
    async with db.transaction() as tx:
        await tx.execute("UPDATE cities SET gold = 500 WHERE id = ?", (pc.id,))
    with pytest.raises(GameError, match="فقط"):
        await services.city.withdraw(poor, 1_000)


async def test_a_gift_for_everybody_tells_each_hero(h, services, db):
    await hero(services, 1, "آرش")
    await hero(services, 2, "دومی")
    await services.admin.give_all(999, gold=500, crystal=3)
    h.session.reset()
    await notifier.deliver(h.bot, services)
    for chat in (1, 2):
        text = dms(h, chat)[-1]["text"]
        assert "مالک قلمرو" in text and "۵۰۰ سکه" in text and "۳ کریستال" in text

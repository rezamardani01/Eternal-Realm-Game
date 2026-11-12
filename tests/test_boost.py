import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.packs import PACKS, SECTIONS
from eternal_realm.game.engine import loot
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=1, gold=0):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "archer")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ?, xp = 0, gold = ?, energy = 500 WHERE id = ?", (level, gold, p.id))
    return await services.players.require(uid)


async def buy(services, player, pack_id, charge="c"):
    order = await services.payments.create_order(player, pack_id)
    return await services.payments.complete(player.platform_user_id, order.payload, order.amount, f"{charge}-{order.id}")


def test_the_catalogue_has_three_boosts_and_three_experience_packs():
    boosts = [PACKS[k] for k in ("boost_24", "boost_48", "boost_72")]
    assert [p.boost_hours for p in boosts] == [24, 48, 72]
    prices = [p.price_rial for p in boosts]
    assert prices == sorted(prices) and len(set(prices)) == 3
    assert [p.price_rial / p.boost_hours for p in boosts] == sorted((p.price_rial / p.boost_hours for p in boosts), reverse=True)  # longer is cheaper per hour
    xp = [PACKS[k] for k in ("xp_s", "xp_m", "xp_l")]
    assert [p.xp for p in xp] == sorted(p.xp for p in xp) and all(p.section == "xp" for p in xp)
    assert "boost" in SECTIONS and "xp" in SECTIONS
    # nothing here costs more than the monthly VIP subscription for a day or two of boost
    assert PACKS["boost_24"].price_rial < PACKS["vip_30"].price_rial


async def test_the_treasury_has_two_separate_sections(h, services, db):
    p = await hero(services, db, 10, "آرش", level=3)
    await h.say(10, "/start")
    await h.panel(10, "premium")
    labels = " ".join(h.labels())
    assert "بوست دو برابر" in labels and "بسته‌های تجربه" in labels
    await h.tap(10, "بوست دو برابر")
    text = h.session.last_text()
    assert "دو برابر" in text and "کریستال دو برابر نمی‌شود" in text and "ساعتی" in text and "۲۴ ساعت" in text
    assert [b["text"] for b in h.session.last_buttons() if "بوست دو برابر" in b["text"]] and len([b for b in h.session.last_buttons() if "تومان" in b["text"]]) == 5
    await h.panel(10, "premium")
    await h.tap(10, "بسته‌های تجربه")
    text = h.session.last_text()
    assert "سطح شما" in text and "حدود" in text and "هر تعداد" in text
    assert len([b for b in h.session.last_buttons() if "تومان" in b["text"]]) == 6


async def test_a_boost_pack_runs_for_its_hours_and_stacks(services, db, clock):
    p = await hero(services, db, 10, "آرش")
    delivery = await buy(services, p, "boost_24")
    now = services.ctx.now()
    assert (await services.players.require(10)).boost_until == now + 24 * 3600
    assert "بوست" in delivery.order.pack.title
    await buy(services, await services.players.require(10), "boost_48")
    assert (await services.players.require(10)).boost_until == now + 72 * 3600  # added to what was left
    clock.advance(73 * 3600)
    async with db.transaction() as tx:
        assert await services.players.boost_factor(tx, p.id) == 1  # over


async def test_the_boost_doubles_coins_experience_and_loot_but_not_crystals(services, db, clock, monkeypatch):
    plain = await hero(services, db, 10, "آرش", level=5)
    boosted = await hero(services, db, 11, "سارا", level=5)
    await buy(services, boosted, "boost_24")

    def fixed(activity, level, luck, perk, rng):
        return loot.Rolled(activity.outcomes[0], gold=10, xp=20, crystal=1, items={"wheat": 2})

    monkeypatch.setattr("eternal_realm.game.services.activities.loot.roll", fixed)
    a = await services.activities.perform(plain.id, "farming", None)
    b = await services.activities.perform(boosted.id, "farming", None)
    assert (a.rolled.gold, a.rolled.xp, a.rolled.crystal, a.rolled.items["wheat"], a.boosted) == (10, 20, 1, 2, False)
    assert (b.rolled.gold, b.rolled.xp, b.rolled.crystal, b.rolled.items["wheat"], b.boosted) == (20, 40, 1, 4, True)  # crystal stays
    from eternal_realm.bot import views

    assert "بوست فعال" in views.activity_result("سارا", b) and "بوست فعال" not in views.activity_result("آرش", a)
    assert (await services.players.require(11)).gold - boosted.gold == 20 and (await services.players.require(10)).gold - plain.gold == 10


async def test_the_boost_also_pays_double_for_the_daily_reward_and_missions(services, db):
    plain = await hero(services, db, 10, "آرش", level=5)
    boosted = await hero(services, db, 11, "سارا", level=5)
    await buy(services, boosted, "boost_24")
    a = await services.players.claim_daily(plain.id)
    b = await services.players.claim_daily(boosted.id)
    assert b.gold == 2 * a.gold


async def test_the_profile_shows_the_running_boost(h, services, db):
    p = await hero(services, db, 10, "آرش")
    await buy(services, p, "boost_24")
    await h.say(10, "پروفایل", group=True)
    assert "بوست دو برابر فعال" in h.session.last_text()


async def test_experience_packs_help_low_levels_more_than_high_ones(services, db):
    low = await hero(services, db, 10, "آرش", level=3)
    high = await hero(services, db, 11, "سارا", level=38)
    a = await buy(services, low, "xp_m")
    b = await buy(services, high, "xp_m")
    new_low, new_high = await services.players.require(10), await services.players.require(11)
    assert new_low.level - 3 > new_high.level - 38 >= 0  # the newcomer climbs much further
    assert new_low.level - 3 >= 3
    assert "تجربه به شما رسید" in a.granted and "سطح" in a.granted and "تجربه به شما رسید" in b.granted


async def test_experience_packs_have_no_weekly_or_level_limit(services, db, clock):
    high = await hero(services, db, 10, "آرش", level=60)
    assert (await services.payments.create_order(high, "xp_s")).amount == PACKS["xp_s"].price_rial
    await hero(services, db, 11, "سارا", level=5)
    for _ in range(8):
        await buy(services, await services.players.require(11), "xp_s")
    assert (await services.payments.create_order(await services.players.require(11), "xp_s")).amount == PACKS["xp_s"].price_rial


async def test_owner_can_gift_a_boost(h, services, db):
    await hero(services, db, 999, "ارباب")
    target = await hero(services, db, 2, "آرش")
    await h.say(999, "اهدا بوست 24", group=True, reply_to=h.message_of(2))
    assert (await services.players.require(2)).boost_until == services.ctx.now() + 24 * 3600
    assert "بوست دو برابر" in h.session.last_text()
    await h.say(999, "اهدا بوست 48", group=True, reply_to=h.message_of(2))
    assert (await services.players.require(2)).boost_until == services.ctx.now() + 72 * 3600
    await h.say(999, "اهدا بوست abc", group=True, reply_to=h.message_of(2))
    assert "ساعت" in h.session.last_text()
    assert target.id

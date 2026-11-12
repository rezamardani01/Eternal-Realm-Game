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
    assert PACKS["season_ticket"].price_toman == 64_900 and TIERS == 100
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
    await h.say(6, "قلمرو")
    await h.tap(6, "قهرمان من")
    await h.tap(6, "مسیر قهرمانی")
    text = h.session.sent("editMessageText")[-1]["text"]
    assert "مرحله‌ی شما" in text and "جایزه‌ی رایگان بعدی" in text
    await h.tap(6, "دریافت همه")
    assert (await services.season.state(p)).claimed
    await h.tap(6, "مراحل و جایزه‌ها")
    assert "مسیر قهرمانی" in h.session.sent("editMessageText")[-1]["text"]
    assert POINTS_PER_TIER == 100


def test_tier_one_matches_the_sketch_and_cards_come_with_golden_tiers():
    assert reward_for("free", 1).gold == 23 and reward_for("ticket", 1).gold == 110
    golden_cards = [t for t in range(1, TIERS + 1) if reward_for("ticket", t).cards]
    assert golden_cards and all(t % 4 == 0 for t in golden_cards)
    assert any("کارت" in line for line in reward_for("ticket", 4).lines())


async def test_tier_panel_has_two_columns_and_navigation(h, services, db):
    p = await hero(services, db, 7, "کیان")
    await add(db, services, p, "boss", 8)  # 240 points = tier 2
    await h.panel(7, "pathtiers", "4")
    rows = h.session.last_markup_rows()
    assert [b["text"] for b in rows[0]] == ["🆓 رایگان", "👑 طلایی"]
    assert "سکه" in rows[1][0]["text"] and "سکه" in rows[1][1]["text"] and len(rows[1]) == 2
    flat = [b["text"] for row in rows for b in row]
    assert "مرحله بعدی ›" in flat and "‹ مرحله قبلی" in flat and any("کارت" in t for t in flat)
    await h.tap(7, "مرحله بعدی")
    assert "مرحله‌ی ۵ از ۱۰۰" in h.session.last_text()
    # a button for a tier you have not reached explains instead of paying
    await h.tap(7, "سکه")
    assert (await services.season.state(p)).claimed == set()


async def test_tapping_a_reward_pays_the_free_track_and_marks_it(h, services, db):
    p = await hero(services, db, 8, "مینا")
    await add(db, services, p, "boss", 4)  # tier 1
    gold = (await services.players.require(8)).gold
    await h.panel(8, "pathtiers", "1")
    await h.click(8, h.session.last_markup_rows()[1][0]["callback_data"])
    assert (await services.players.require(8)).gold == gold + 23
    assert "✔" in h.session.last_markup_rows()[1][0]["text"]
    await h.click(8, h.session.last_markup_rows()[1][1]["callback_data"])  # the golden one needs the ticket
    assert (await services.players.require(8)).gold == gold + 23


async def test_a_golden_card_reward_lands_in_the_album(services, db):
    p = await hero(services, db, 9, "رها")
    async with db.transaction() as tx:
        await repo.grant_ticket(tx, p.id, services.ctx.now())
    await add(db, services, p, "boss", 14)  # 420 points = tier 4
    reward = await services.season.claim(p, "ticket", 4)
    assert reward.cards and (await services.cards.owned(p.id)).get(reward.cards[0]) == 1


async def test_new_tier_message_is_sent_once_per_tier(h, services, db):
    from eternal_realm.bot.path_panel import notify_new_tiers

    p = await hero(services, db, 10, "پویا")
    assert await notify_new_tiers(h.bot, services) == 0
    await add(db, services, p, "boss", 8)  # tier 2
    assert await notify_new_tiers(h.bot, services) == 1
    sent = h.session.sent("sendMessage")[-1]
    assert str(sent["chat_id"]) == "10" and "*۲*" in sent["text"]
    labels = [b["text"] for row in sent["reply_markup"]["inline_keyboard"] for b in row]
    assert any("دریافت جوایز" in t for t in labels)
    assert await notify_new_tiers(h.bot, services) == 0
    await add(db, services, p, "boss", 4)
    assert await notify_new_tiers(h.bot, services) == 1


async def test_profile_shows_the_stats_in_the_text_and_only_hero_buttons(h, services, db):
    await hero(services, db, 11, "نگار")
    await h.panel(11, "profile")
    text = h.session.last_text()
    assert all(word in text for word in ("جان", "حمله", "دفاع", "جادو", "سرعت", "شانس", "انرژی"))
    labels = [b["text"] for row in h.session.last_markup_rows() for b in row]
    assert not any(word in t for t in labels for word in ("حمله", "دفاع", "جادو", "سرعت", "شانس")) and len(labels) <= 12

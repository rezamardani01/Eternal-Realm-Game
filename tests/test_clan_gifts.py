"""A clan-mate buys something with real money: everybody else in the clan finds a small thank-you box."""

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.items import ITEMS
from eternal_realm.game.services import clan_gifts
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "archer")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=10_000, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def clan_of_three(services, db):
    leader, a, b = await hero(services, db, 1, "رهبر"), await hero(services, db, 2, "سارا"), await hero(services, db, 3, "بهرام")
    clan = await services.clans.create(leader, "شیرها")
    await services.clans.join(a, clan.id)
    await services.clans.join(b, clan.id)
    return leader, a, b


async def buy(services, player, pack_id):
    order = await services.payments.create_order(player, pack_id)
    return await services.payments.complete(player.platform_user_id, order.payload, order.amount, f"ch-{order.id}")


def test_every_item_in_the_boxes_exists_and_the_tiers_climb():
    for draws, table, gold, crystal in clan_gifts.LOOT:
        assert draws[0] <= draws[1] and gold[0] < gold[1] and 0 <= crystal <= 1
        assert all(item in ITEMS and low <= high and weight > 0 for item, low, high, weight in table)
    assert [t[0] for t in clan_gifts.TIERS] == sorted(t[0] for t in clan_gifts.TIERS)
    assert [clan_gifts.tier_of(x) for x in (50_000, 100_000, 299_990, 300_000, 700_000, 2_000_000)] == [0, 1, 1, 2, 3, 3]
    assert len(clan_gifts.LOOT) == len(clan_gifts.TIERS)
    # the dearer the purchase, the richer the box (on average)
    assert [c[2][1] for c in clan_gifts.LOOT] == sorted(c[2][1] for c in clan_gifts.LOOT)


async def test_a_purchase_leaves_a_box_for_every_other_clan_mate_with_a_message_and_a_button(services, db):
    leader, a, b = await clan_of_three(services, db)
    await buy(services, a, "crystal_m")
    async with db.read() as tx:
        boxes = await tx.fetchall("SELECT player_id, tier, from_name, clan_name FROM clan_gift_boxes ORDER BY player_id")
    assert [(r["player_id"], r["tier"]) for r in boxes] == [(leader.id, 2), (b.id, 2)]  # the buyer gets none
    assert boxes[0]["from_name"] == "سارا" and boxes[0]["clan_name"] == "شیرها"
    alerts = await services.alerts.pending()
    mine = [x for x in alerts if x.screen == "cgopen"]
    assert len(mine) == 2
    text = mine[0].text
    assert "سارا" in text and "شیرها" in text and "قدردانی" in text and "هدیه‌ی بزرگ" in text
    assert mine[0].arg.isdigit()


async def test_opening_a_box_pays_once_and_only_to_its_owner(h, services, db):
    leader, a, b = await clan_of_three(services, db)
    await buy(services, a, "coins_s")
    async with db.read() as tx:
        box = await tx.fetchone("SELECT id FROM clan_gift_boxes WHERE player_id = ?", (leader.id,))
    with pytest.raises(GameError, match="برای شما نیست"):
        await services.clan_gifts.open(b, box["id"])
    gold = (await services.players.require(1)).gold
    await h.panel(1, "cgopen", str(box["id"]))
    text = h.session.last_text()
    assert "هدیه‌ی خاندان باز شد" in text and "سارا" in text and "داخلش بود" in text
    assert (await services.players.require(1)).gold > gold
    with pytest.raises(GameError, match="قبلاً"):
        await services.clan_gifts.open(leader, box["id"])
    assert await services.clan_gifts.waiting(leader.id) == 0 and await services.clan_gifts.waiting(b.id) == 1


async def test_a_bigger_purchase_gives_a_bigger_box(services, db):
    leader, a, b = await clan_of_three(services, db)
    small = await buy(services, a, "coins_s")
    big = await buy(services, a, "pet_dragon")
    async with db.read() as tx:
        tiers = [r["tier"] for r in await tx.fetchall("SELECT tier FROM clan_gift_boxes WHERE player_id = ? ORDER BY id", (leader.id,))]
    assert tiers == [0, 3] and small and big
    from eternal_realm.game.services.clan_gifts import ClanGiftService

    def average_gold(tier):
        draws, table, gold, crystal = clan_gifts.LOOT[tier]
        return sum(gold) / 2

    assert average_gold(3) > average_gold(0) * 5


async def test_nothing_happens_without_a_clan_and_a_repeated_payment_does_not_repeat_the_boxes(services, db):
    lone = await hero(services, db, 7, "تنها")
    await buy(services, lone, "coins_s")
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM clan_gift_boxes", (), 0) == 0
    leader, a, b = await clan_of_three(services, db)
    order = await services.payments.create_order(a, "coins_s")
    await services.payments.complete(2, order.payload, order.amount, "ch-x")
    again = await services.payments.complete(2, order.payload, order.amount, "ch-x")
    assert again.duplicate
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM clan_gift_boxes", (), 0) == 2


async def test_a_member_gets_at_most_three_boxes_a_day_and_gifts_for_others_also_count(services, db, clock):
    leader, a, b = await clan_of_three(services, db)
    for _ in range(5):
        await buy(services, a, "coins_s")
    assert await services.clan_gifts.waiting(leader.id) == clan_gifts.DAILY_BOXES
    clock.advance(86400)
    await buy(services, a, "coins_s")
    assert await services.clan_gifts.waiting(leader.id) == clan_gifts.DAILY_BOXES + 1


async def test_the_delivery_loop_sends_the_message_with_an_open_button(h, services, db):
    from eternal_realm.bot import notifier

    leader, a, b = await clan_of_three(services, db)
    await buy(services, a, "crystal_s")
    h.session.reset()
    await notifier.deliver(h.bot, services)
    buttons = [btn for m in h.session.sent("sendMessage") for row in m.get("reply_markup", {}).get("inline_keyboard", []) for btn in row]
    assert sum("باز کردن هدیه" in btn["text"] for btn in buttons) == 2
    await h.click(1, next(btn for btn in buttons if "باز کردن هدیه" in btn["text"])["callback_data"])
    assert "هدیه‌ی خاندان باز شد" in h.session.last_text()


async def test_the_clan_card_in_a_group_ends_with_the_exit_button_and_no_back(h, services, db):
    leader, a, b = await clan_of_three(services, db)
    await h.say(1, "خاندان", group=True)
    rows = h.session.last_markup_rows()
    assert "خروج از خاندان" in rows[-1][0]["text"] and not any("بازگشت" in btn["text"] for row in rows for btn in row)
    await h.panel(1, "clan")  # in the private chat the way back stays
    assert any("بازگشت" in btn["text"] for row in h.session.last_markup_rows() for btn in row)

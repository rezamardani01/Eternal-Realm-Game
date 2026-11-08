import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.packs import ORDER_TTL_SECONDS, PACKS
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def reg(services, uid=10, name="آرش"):
    return await services.players.register(uid, "u", name, "elf", "archer")


def test_pack_catalogue_is_valid():
    from eternal_realm.game.data.items import ITEMS

    for pack in PACKS.values():
        assert len(pack.title) <= 32 and pack.price_rial > 0 and pack.price_rial % 10 == 0
        assert pack.gold or pack.crystal or pack.items or pack.lucky
        assert all(item in ITEMS for item in pack.items)


async def test_full_payment_flow_delivers_once(services):
    p = await reg(services)
    order = await services.payments.create_order(p, "crystal_s")
    assert await services.payments.check_precheckout(10, order.payload, order.amount) is None

    first = await services.payments.complete(10, order.payload, order.amount, "ch-1")
    assert not first.duplicate and first.order.status == "delivered"
    assert (await services.players.require(10)).crystal == 20

    again = await services.payments.complete(10, order.payload, order.amount, "ch-1")  # repeated callback
    assert again.duplicate
    assert (await services.players.require(10)).crystal == 20
    assert await services.payments.check_precheckout(10, order.payload, order.amount) is not None


async def test_bundle_delivers_gold_and_items(services):
    p = await reg(services)
    order = await services.payments.create_order(p, "adventurer")
    await services.payments.complete(10, order.payload, order.amount, "ch-2")
    after = await services.players.require(10)
    assert after.gold == p.gold + PACKS["adventurer"].gold
    stacks = {i.id: q for i, q in (await services.inventory.view(p.id)).stacks}
    assert stacks["big_energy_potion"] == 5
    assert any(g.item.id == "steel_sword" for g in (await services.inventory.view(p.id)).gear)


async def test_precheckout_rejects_wrong_user_amount_unknown_and_expired(services, clock):
    p = await reg(services)
    await reg(services, 11, "سارا")
    order = await services.payments.create_order(p, "coins_s")
    assert await services.payments.check_precheckout(11, order.payload, order.amount)  # other user
    assert await services.payments.check_precheckout(10, order.payload, order.amount - 10)  # wrong amount
    assert await services.payments.check_precheckout(10, "ER-nope", order.amount)  # unknown
    clock.advance(ORDER_TTL_SECONDS + 1)
    assert await services.payments.check_precheckout(10, order.payload, order.amount)  # expired


async def test_mismatched_payment_is_not_delivered(services):
    p = await reg(services)
    order = await services.payments.create_order(p, "coins_m")
    with pytest.raises(GameError):
        await services.payments.complete(10, order.payload, order.amount - 10, "x")
    with pytest.raises(GameError):
        await services.payments.complete(99, order.payload, order.amount, "y")
    with pytest.raises(GameError):
        await services.payments.complete(10, "ER-unknown", 1, "z")
    assert (await services.players.require(10)).gold == p.gold


async def test_late_payment_of_an_expired_order_is_still_honoured(services, clock):
    p = await reg(services)
    order = await services.payments.create_order(p, "coins_s")
    clock.advance(ORDER_TTL_SECONDS + 5)
    assert await services.payments.expire_stale() == 1
    await services.payments.complete(10, order.payload, order.amount, "late")  # money was taken
    assert (await services.players.require(10)).gold == p.gold + 5_000


async def test_disabled_payments_and_unknown_pack(services):
    p = await reg(services)
    with pytest.raises(GameError):
        await services.payments.create_order(p, "nope")
    object.__setattr__(services.ctx.settings, "payments_enabled", False)
    with pytest.raises(GameError):
        await services.payments.create_order(p, "coins_s")


async def test_invoice_flow_through_the_bot(h, services):
    p = await reg(services)
    await h.say(10, "/start")
    await h.panel(10, "premium")
    assert "خزانه‌ی ویژه" in h.session.last_text()
    assert len(h.labels()) == 7  # six sections and a back button
    await h.tap(10, "خرید کریستال")
    assert "تومان" in h.session.last_text()
    await h.click(10, h.button_data("۲۰ کریستال"))
    invoice = h.session.sent("sendInvoice")[-1]
    assert invoice["provider_token"].startswith("WALLET-")
    assert invoice["prices"] == [{"label": "۲۰ کریستال", "amount": 100_000}]
    payload = invoice["payload"]

    await h.precheckout(10, payload, 100_000)
    answer = h.session.sent("answerPreCheckoutQuery")[-1]
    assert answer["ok"] is True

    await h.paid(10, payload, 100_000, "wallet-abc")
    assert any("پرداخت موفق بود" in t for t in h.session.texts())
    assert (await services.players.require(10)).crystal == 20

    await h.paid(10, payload, 100_000, "wallet-abc")  # Bale re-delivers the update
    assert (await services.players.require(10)).crystal == 20
    assert p


async def test_precheckout_is_declined_for_a_tampered_amount(h, services):
    p = await reg(services)
    order = await services.payments.create_order(p, "coins_s")
    await h.precheckout(10, order.payload, 1)
    answer = h.session.sent("answerPreCheckoutQuery")[-1]
    assert answer["ok"] is False and answer["error_message"]


async def test_cannot_buy_from_a_group_and_crystal_chest_button(h, services, db):
    await reg(services)
    await h.click(10, "buy:cash:coins_s", group=True)
    assert any("پیام خصوصی" in c.get("text", "") for c in h.session.callback_answers())

    from eternal_realm.db.repos import wallet

    player_id = (await services.players.require(10)).id  # never call services while a tx is open
    async with db.transaction() as tx:
        await wallet.apply(tx, player_id, crystal=30, reason="t", now=1)
    await h.panel(10, "cbuyq", "magic_chest")
    assert "تأیید خرید" in h.session.last_text()
    await h.tap(10, "بله")
    stacks = {i.id: q for i, q in (await services.inventory.view(1)).stacks}
    assert stacks["magic_chest"] == 1


async def test_premium_hub_has_four_sections_each_with_its_own_text(h, services):
    await reg(services)
    await h.panel(10, "premium")
    labels = h.labels()
    for word in ("خرید سکه", "خرید کریستال", "خرید بسته", "خرید صندوق", "خرید مواد"):
        assert any(word in t for t in labels), word
    assert all("منو" not in t for t in labels)

    await h.tap(10, "خرید سکه")
    assert "سلاح" in h.session.last_text() and "تومان" in h.session.last_text()
    await h.tap(10, "بازگشت")
    await h.tap(10, "خرید بسته")
    assert "شامل" in h.session.last_text()
    await h.tap(10, "بازگشت")
    await h.tap(10, "خرید صندوق")
    text = h.session.last_text()
    assert "گنجی پنهان" in text and "\n\n• 🎁" in text  # one blank line between entries
    assert not any("شانس" in x for x in h.labels())  # the odds live in the confirm page instead
    await h.tap(10, "صندوقچه جادویی")
    assert "٪" in h.session.last_text() and "موجودی" in h.session.last_text()
    await h.tap(10, "نه")
    assert "خرید صندوق" in h.session.last_text()


async def test_owner_gets_a_complete_sale_report(h, services):
    p = await reg(services)
    order = await services.payments.create_order(p, "adventurer")
    await h.paid(10, order.payload, order.amount, "TRACK-77")
    reports = [m for m in h.session.sent("sendMessage") if m["chat_id"] == 1]  # owner_id of the test settings
    assert len(reports) == 1
    text = reports[0]["text"]
    for needle in ("فروش جدید", "بسته ماجراجو", "بسته‌ی ویژه", "۱۵٬۰۰۰ تومان", "آرش", "TRACK-77", "@u10",
                   "شناسه بله", "تاریخ", "ساعت", "جمع فروش"):
        assert needle in text, needle
    assert text.split("\n")[0].startswith("💰")

    await h.paid(10, order.payload, order.amount, "TRACK-77")  # a repeated update sends no second report
    assert len([m for m in h.session.sent("sendMessage") if m["chat_id"] == 1]) == 1


# --- iron ore and the daily lucky bundles ------------------------------------------------------
async def test_iron_ore_packs_deliver_ore(services):
    p = await reg(services)
    order = await services.payments.create_order(p, "ore_m")
    await services.payments.complete(10, order.payload, order.amount, "ore-1")
    stacks = {i.id: q for i, q in (await services.inventory.view(p.id)).stacks}
    assert stacks["iron_ore"] == 100


async def test_lucky_bundle_gives_guaranteed_gold_and_prizes_from_todays_theme(services, clock):
    from eternal_realm.game.data import lucky

    p = await reg(services)
    before = (await services.players.require(10)).gold
    order = await services.payments.create_order(p, "lucky_m")
    result = await services.payments.complete(10, order.payload, order.amount, "lucky-1")
    assert result.granted and "سکه" in result.granted
    gained = (await services.players.require(10)).gold - before
    assert gained >= lucky.TIERS["lucky_m"].guaranteed_gold
    theme = lucky.theme_of_day(services.ctx.now())
    allowed = {pr.item_id for pr in theme.prizes if pr.item_id}
    got = {i.id for i, _ in (await services.inventory.view(p.id)).stacks} | {
        g.item.id for g in (await services.inventory.view(p.id)).gear
    }
    assert (got - {"energy_potion", "short_bow"}) <= allowed | {"big_energy_potion"} | allowed


def test_theme_changes_every_day_and_odds_sum_to_one():
    from eternal_realm.game.data import lucky
    from eternal_realm.game.data.items import ITEMS

    days = {lucky.theme_of_day(d * 86400).id for d in range(3)}
    assert len(days) == 3
    for theme in lucky.THEMES:
        assert abs(sum(share for _, share in lucky.odds(theme)) - 1) < 1e-9
        assert all(pr.item_id is None or pr.item_id in ITEMS for pr in theme.prizes)


async def test_bundles_screen_shows_lucky_packs_and_their_odds(h, services):
    await reg(services)
    await h.panel(10, "prem", "bundles")
    assert "بسته‌های شانسی امروز" in h.session.last_text()
    assert sum("شانسی" in t for t in h.labels()) >= 3
    await h.tap(10, "شانس‌های امروز")
    assert "٪" in h.session.last_text() and "تضمینی" in h.session.last_text()


async def test_lucky_purchase_through_the_bot_shows_what_was_inside(h, services):
    p = await reg(services)
    order = await services.payments.create_order(p, "lucky_s")
    await h.paid(10, order.payload, order.amount, "LK-1")
    assert any("این‌ها از بسته درآمد" in t for t in h.session.texts())
    owner_report = [m["text"] for m in h.session.sent("sendMessage") if m["chat_id"] == 1][0]
    assert "محتوای تصادفی" in owner_report

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
        assert pack.gold or pack.crystal or pack.items
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
    assert "خزانه‌ی ویژه" in h.session.last_text() and "تومان" in h.session.last_text()
    await h.click(10, h.button_data("۱۰۰ کریستال") if False else "buy:cash:crystal_s")
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

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.deals import DEALS_PER_DAY, daily_deals, discounted, find_deal, seconds_left
from eternal_realm.game.data.items import ITEMS
from eternal_realm.game.data.packs import PACKS
from eternal_realm.shared.errors import GameError

from .harness import Harness

NOW = 1_700_000_000


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


def test_every_pack_references_real_items_and_deal_prices_are_valid():
    for pack in PACKS.values():
        assert all(i in ITEMS for i in pack.items), pack.id
        assert len(pack.title) <= 32 and pack.price_rial % 10 == 0
    for day in range(40):
        for deal in daily_deals(NOW + day * 86400):
            assert 10_000 <= deal.price_rial < deal.pack.price_rial or deal.price_rial == 10_000
            assert deal.price_rial % 10 == 0 and deal.percent in (20, 25, 30, 40, 50)


def test_deals_are_the_same_all_day_and_change_tomorrow():
    start = (NOW + 12600) // 86400 * 86400 - 12600  # Tehran midnight
    morning, evening = start + 3600, start + 80_000
    a = [(d.pack.id, d.percent) for d in daily_deals(morning)]
    assert a == [(d.pack.id, d.percent) for d in daily_deals(evening)] and len(a) == DEALS_PER_DAY
    assert a != [(d.pack.id, d.percent) for d in daily_deals(morning + 86400)]
    assert 0 < seconds_left(NOW) <= 86400


def test_discount_rounding():
    assert discounted(100_000, 50) == 50_000 and discounted(40_000, 50) == 20_000 and discounted(15_000, 50) == 10_000


async def test_buying_a_deal_charges_the_discounted_price_and_delivers(services, clock):
    p = await services.players.register(10, "u", "آرش", "elf", "archer")
    deal = daily_deals(services.ctx.now())[0]
    order = await services.payments.create_order(p, deal.pack.id, deal=True)
    assert order.amount == deal.price_rial < deal.pack.price_rial
    assert await services.payments.check_precheckout(10, order.payload, deal.pack.price_rial) is not None  # full price
    assert await services.payments.check_precheckout(10, order.payload, deal.price_rial) is None
    done = await services.payments.complete(10, order.payload, deal.price_rial, "d-1")
    assert not done.duplicate


async def test_a_pack_that_is_not_on_sale_today_cannot_be_bought_as_a_deal(services):
    p = await services.players.register(10, "u", "آرش", "elf", "archer")
    today = {d.pack.id for d in daily_deals(services.ctx.now())}
    other = next(pid for pid, pack in PACKS.items() if pid not in today and not pack.lucky)
    with pytest.raises(GameError, match="تخفیف"):
        await services.payments.create_order(p, other, deal=True)
    assert find_deal(services.ctx.now(), other) is None


async def test_deal_expires_at_midnight(services, clock):
    p = await services.players.register(10, "u", "آرش", "elf", "archer")
    deal = daily_deals(services.ctx.now())[0]
    clock.advance(seconds_left(services.ctx.now()) + 5)
    tomorrow = {d.pack.id for d in daily_deals(services.ctx.now())}
    if deal.pack.id not in tomorrow:
        with pytest.raises(GameError):
            await services.payments.create_order(p, deal.pack.id, deal=True)


async def test_deals_screen_and_invoice_flow(h, services):
    await services.players.register(10, "u", "آرش", "elf", "archer")
    await h.panel(10, "premium")
    await h.tap(10, "تخفیف‌های امروز")
    text = h.session.last_text()
    assert "تخفیف‌های امروز" in text and "قبلاً" in text and "اکنون" in text and text.count("\n\n") >= 4
    deals = daily_deals(services.ctx.now())
    assert len([t for t in h.labels() if "٪-" in t]) == len(deals)
    await h.tap(10, deals[0].pack.title)
    invoice = h.session.sent("sendInvoice")[-1]
    assert invoice["prices"][0]["amount"] == deals[0].price_rial
    assert "تخفیف" in invoice["description"]
    await h.paid(10, invoice["payload"], deals[0].price_rial, "DEAL-1")
    report = [m["text"] for m in h.session.sent("sendMessage") if m["chat_id"] == 1][0]
    assert "با تخفیف" in report and "قیمت عادی" in report

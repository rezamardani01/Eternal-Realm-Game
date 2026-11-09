import re

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.shared.errors import GameError
from eternal_realm.shared.text import EMOJI

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def rich(services, db, uid=7, gold=100_000, crystal=0):
    p = await services.players.register(uid, f"u{uid}", f"آرش{uid}", "elf", "archer")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, crystal=crystal, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


async def test_the_prices_include_the_fee(services):
    ex = services.exchange
    assert ex.buy_quote(10).gold == 10 * 600 + 600 and ex.buy_quote(10).fee == 600
    assert ex.sell_quote(10).gold == 10 * 600 - 600
    assert ex.buy_quote(1).gold > ex.rate > ex.sell_quote(1).gold  # a round trip always loses the fees


async def test_buying_and_selling_move_both_purses_and_log_the_fee(services, db):
    p = await rich(services, db)
    start = p.gold
    q = await services.exchange.buy(p, 5)
    p = await services.players.require(7)
    assert p.crystal == 5 and p.gold == start - q.gold
    q2 = await services.exchange.sell(p, 5)
    p = await services.players.require(7)
    assert p.crystal == 0 and p.gold == start - q.gold + q2.gold
    assert await services.exchange.fees_collected() == q.fee + q2.fee > 0
    with pytest.raises(GameError):  # no crystals left
        await services.exchange.sell(p, 1)
    with pytest.raises(GameError, match="مقدار"):
        await services.exchange.buy(p, 3)


async def test_poor_heroes_and_the_daily_limit(services, db, clock):
    poor = await rich(services, db, gold=100)
    with pytest.raises(GameError):
        await services.exchange.buy(poor, 1)
    p = await rich(services, db, uid=8, gold=10_000_000)
    for _ in range(2):
        await services.exchange.buy(p, 50)
    with pytest.raises(GameError, match="سقف"):
        await services.exchange.buy(p, 1)
    assert await services.exchange.left_today(p.id) == 0
    clock.advance(86400 + 5)
    await services.exchange.buy(p, 1)


async def test_the_screens(h, services, db):
    await rich(services, db, crystal=3)
    await h.panel(7, "home")
    assert any("بازار و تجارت" in label for label in h.labels())
    await h.panel(7, "trade")
    assert any("مرکز مبادله" in label for label in h.labels())
    await h.panel(7, "exch")
    text = h.session.last_text()
    assert "کارمزد" in text and {"تبدیل سکه به کریستال", "تبدیل کریستال به سکه"} <= {
        w.strip("🪙💎 ") for w in (b["text"] for b in h.session.last_buttons())
    }
    for line in text.splitlines():
        assert len(re.findall(EMOJI, line)) <= 1, line
    await h.panel(7, "exchbuyq", "5")
    assert "تأیید خرید" in h.session.last_text()
    await h.panel(7, "exchbuyok", "5")
    assert (await services.players.require(7)).crystal == 8
    await h.panel(7, "exchsellq", "5")
    assert "تأیید فروش" in h.session.last_text()
    await h.panel(7, "exchsellok", "5")
    assert (await services.players.require(7)).crystal == 3

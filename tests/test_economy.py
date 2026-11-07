import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def pair(services, db, rich=10_000):
    a = await services.players.register(10, "a", "آرش", "elf", "archer")
    b = await services.players.register(11, "b", "سارا", "fairy", "mage")
    async with db.transaction() as tx:
        await wallet.apply(tx, a.id, gold=rich, reason="test", now=services.ctx.now())
    return await services.players.require(10), await services.players.require(11)


async def total_gold(services):
    return (await services.players.require(10)).gold + (await services.players.require(11)).gold


async def test_transfer_conserves_gold(services, db):
    a, b = await pair(services, db)
    before = await total_gold(services)
    await services.economy.transfer(a, b, 700)
    assert await total_gold(services) == before
    assert (await services.players.require(11)).gold == b.gold + 700


async def test_transfer_rules(services, db):
    a, b = await pair(services, db)
    with pytest.raises(GameError):
        await services.economy.transfer(a, a, 100)
    with pytest.raises(GameError):
        await services.economy.transfer(a, b, 1)  # below the minimum
    with pytest.raises(wallet.InsufficientFunds):
        await services.economy.transfer(b, a, 20_000)  # within the limit but more than b owns
    limit = services.ctx.balance.transfer_daily_limit
    assert limit >= 10_000
    async with db.transaction() as tx:
        await wallet.apply(tx, a.id, gold=limit * 2, reason="test", now=services.ctx.now())
    a = await services.players.require(10)
    await services.economy.transfer(a, b, limit - 10)
    with pytest.raises(GameError, match="سقف"):
        await services.economy.transfer(a, b, 100)


async def test_daily_limit_resets_next_day(services, db, clock):
    a, b = await pair(services, db, rich=200_000)
    limit = services.ctx.balance.transfer_daily_limit
    await services.economy.transfer(a, b, limit)
    clock.advance(24 * 3600 + 1)
    await services.economy.transfer(await services.players.require(10), b, 100)


async def test_transfer_command_by_reply(h, services, db):
    await pair(services, db)
    await h.say(10, "انتقال 500", group=True, reply_to=h.message_of(11))
    assert "فرستاد" in h.session.last_text()
    await h.say(10, "انتقال", group=True, reply_to=h.message_of(11))
    assert "ریپلای" in h.session.last_text()
    await h.say(10, "انتقال 500", group=True)
    assert "ریپلای" in h.session.last_text()


async def test_wallet_command(h, services, db):
    await pair(services, db)
    await h.say(11, "کیف پول", group=True)
    assert "سکه" in h.session.last_text() and "کریستال" in h.session.last_text()

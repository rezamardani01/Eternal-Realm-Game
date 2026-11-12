import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.services.economy import CRYSTAL_DAILY_LIMIT
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
    with pytest.raises(GameError, match="خزانه‌دار"):
        await services.economy.transfer(a, b, 100)


async def test_daily_limit_resets_next_day(services, db, clock):
    limit = services.ctx.balance.transfer_daily_limit
    a, b = await pair(services, db, rich=limit + 100_000)
    await services.economy.transfer(a, b, limit)
    clock.advance(24 * 3600 + 1)
    await services.economy.transfer(await services.players.require(10), b, 100)


async def test_transfer_panel_flow_for_gold(h, services, db):
    await pair(services, db)
    before = [(await services.players.require(u)).gold for u in (10, 11)]
    await h.say(10, "انتقال", group=True, reply_to=h.message_of(11))
    assert "انتقال هدیه" in h.session.last_text()
    await h.tap(10, "سکه", group=True)
    await h.tap(10, "+۵", group=True)
    await h.tap(10, "+۱", group=True)
    assert "۱۶" in h.session.last_text() and "مقدار هدیه" in h.session.last_text()
    await h.tap(10, "+۱٬۰۰۰", group=True)
    await h.tap(10, "تأیید مقدار", group=True)
    assert "مطمئنید" in h.session.last_text()
    assert (await services.players.require(10)).gold == before[0]  # nothing moved yet
    await h.tap(10, "تأیید و انتقال", group=True)
    assert "با موفقیت رسید" in h.session.last_text()
    assert (await services.players.require(10)).gold == before[0] - 1_016
    assert (await services.players.require(11)).gold == before[1] + 1_016
    dm = [c for c in h.session.sent("sendMessage") if str(c["chat_id"]) == "11"]
    assert dm and "هدیه‌ای برای شما رسید" in dm[-1]["text"] and "۱٬۰۱۶" in dm[-1]["text"]


async def test_transfer_panel_cancel_and_other_users_cannot_press(h, services, db):
    await pair(services, db)
    before = (await services.players.require(10)).gold
    await h.say(10, "انتقال 500", group=True, reply_to=h.message_of(11))
    assert "مقدار هدیه" in h.session.last_text()
    data = h.button_data("تأیید مقدار")
    await h.click(11, data, group=True)
    assert any("مال شما نیست" in a.get("text", "") for a in h.session.callback_answers())
    await h.tap(10, "انصراف", group=True)
    assert "لغو شد" in h.session.last_text() and (await services.players.require(10)).gold == before


async def test_transfer_crystals_and_items(services, db):
    a, b = await pair(services, db)
    async with db.transaction() as tx:
        await wallet.apply(tx, a.id, crystal=30, reason="t", now=services.ctx.now())
        await services.inventory.grant(tx, a.id, "iron_ore", 5)
    me = await services.players.require(10)
    receipt = await services.economy.send(me, b, "crystal", 12)
    assert receipt.left == CRYSTAL_DAILY_LIMIT - 12 and (await services.players.require(11)).crystal == 12
    await services.economy.send(me, b, "iron_ore", 3)
    stacks = {i.id: q for i, q in (await services.inventory.view(b.id)).stacks}
    assert stacks["iron_ore"] == 3
    with pytest.raises(GameError):
        await services.economy.send(me, b, "iron_ore", 50)
    with pytest.raises(GameError):
        await services.economy.send(me, b, "rename_ticket", 1)  # tickets cannot be traded


async def test_transfer_without_reply_explains(h, services, db):
    await pair(services, db)
    await h.say(10, "انتقال", group=True)
    assert "ریپلای" in h.session.last_text()


async def test_wallet_command(h, services, db):
    await pair(services, db)
    await h.say(11, "کیف پول")
    assert "سکه" in h.session.last_text() and "کریستال" in h.session.last_text()

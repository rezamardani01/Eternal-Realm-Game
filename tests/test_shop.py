import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.items import get_item
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def reg(services, uid=10, name="آرش"):
    return await services.players.register(uid, "u", name, "dwarf", "warrior")


async def give(services, db, pid, item_id, qty=1):
    async with db.transaction() as tx:
        return await services.inventory.grant(tx, pid, item_id, qty)


async def fund(services, db, pid, gold):
    async with db.transaction() as tx:
        await wallet.apply(tx, pid, gold=gold, reason="test", now=services.ctx.now())


async def test_buy_and_sell_roundtrip(services):
    p = await reg(services)
    paid = await services.shop.buy(p, get_item("energy_potion"), 3)
    assert paid == 360
    assert (await services.players.require(10)).gold == p.gold - 360
    got = await services.shop.sell_stack(p, get_item("energy_potion"), 3)
    assert got == 120 and (await services.players.require(10)).gold == p.gold - 240


async def test_cannot_buy_without_money_or_oversell(services):
    p = await reg(services)
    with pytest.raises(wallet.InsufficientFunds):
        await services.shop.buy(p, get_item("grand_energy_potion"), 1)
    with pytest.raises(GameError):
        await services.shop.sell_stack(p, get_item("energy_potion"), 50)
    with pytest.raises(GameError):
        await services.shop.buy(p, get_item("dragon_scale"), 1)  # not sold by NPCs
    with pytest.raises(GameError):
        await services.shop.buy(p, get_item("energy_potion"), 0)
    assert (await services.players.require(10)).gold == p.gold


async def test_potions_can_be_bought_again_and_again(services, db):
    p = await reg(services)
    await fund(services, db, p.id, 5_000)
    p = await services.players.require(10)
    for _ in range(3):
        await services.shop.buy(p, get_item("energy_potion"), 3)
    assert (await services.inventory.view(p.id)).stack_qty("energy_potion") >= 9


async def test_selling_a_stack_needs_confirmation(services, db, h):
    p = await reg(services)
    await give(services, db, p.id, "stone", 4)
    before = (await services.players.require(10)).gold
    await h.panel(10, "isellq", "stone", "all")
    assert "تأیید فروش" in h.session.last_text() and (await services.players.require(10)).gold == before
    await h.tap(10, "بله، بفروش")
    assert (await services.players.require(10)).gold == before + 4 * get_item("stone").sell


async def test_shop_categories_have_two_columns_name_and_price(h, services):
    await services.players.register(7, "u", "آرش", "elf", "archer")
    await h.say(7, "فروشگاه")
    for category in ("معجون",):
        await h.tap(7, category)
        rows = [row for row in h.session.last_markup_rows() if any("shopitem" in b.get("callback_data", "") for b in row)]
        assert rows and all(len(row) == 2 for row in rows)
        assert all(row[0]["callback_data"] == row[1]["callback_data"] for row in rows)  # both buttons open the item
        assert any(("🪙" in row[1]["text"] or "دارید" in row[1]["text"]) for row in rows)
        await h.tap(7, "بازگشت")


def test_the_shop_no_longer_sells_any_gear():
    from eternal_realm.game.data.items import Kind
    from eternal_realm.game.services.shop import shop_items

    assert shop_items() and all(i.kind in (Kind.CONSUMABLE, Kind.MATERIAL) for i in shop_items())

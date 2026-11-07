import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.items import get_item
from eternal_realm.game.services.shop import UPGRADE_CHANCE, upgrade_quote
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
        await services.shop.buy(p, get_item("steel_sword"), 1)
    with pytest.raises(GameError):
        await services.shop.sell_stack(p, get_item("energy_potion"), 50)
    with pytest.raises(GameError):
        await services.shop.buy(p, get_item("fire_sword"), 1)  # not sold by NPCs
    with pytest.raises(GameError):
        await services.shop.buy(p, get_item("energy_potion"), 0)
    assert (await services.players.require(10)).gold == p.gold


async def test_sell_gear_rules(services, db):
    p = await reg(services)
    worn = (await services.inventory.view(p.id)).gear[0]
    with pytest.raises(GameError):
        await services.shop.sell_gear(p, worn.id)  # equipped
    spare = (await give(services, db, p.id, "leather_cap"))[0]
    piece, total = await services.shop.sell_gear(p, spare)
    assert total == piece.item.sell > 0
    with pytest.raises(GameError):
        await services.shop.sell_gear(p, spare)  # already sold


async def test_upgrade_success_and_materials(services, db):
    p = await reg(services)
    gid = (await services.inventory.view(p.id)).gear[0].id
    quote = upgrade_quote(get_item("wooden_sword"), 0)
    await fund(services, db, p.id, quote.gold)
    await give(services, db, p.id, "iron_ore", 5)
    result = await services.shop.upgrade(p, gid, 1)
    assert result.success and result.piece.upgrade == 1
    assert result.piece.stats.atk > get_item("wooden_sword").stats.atk


async def test_failed_upgrade_keeps_the_gear(services, db):
    p = await reg(services)
    gid = (await services.inventory.view(p.id)).gear[0].id
    services.ctx.rng.random = lambda: 0.999  # force a failure on any chance < 1
    await fund(services, db, p.id, 10_000)
    await give(services, db, p.id, "iron_ore", 40)
    for level in range(1, 3):
        assert (await services.shop.upgrade(p, gid, level)).success  # +1 and +2 are guaranteed
    result = await services.shop.upgrade(p, gid, 3)
    assert not result.success and result.piece.upgrade == 2
    assert (await services.inventory.view(p.id)).gear[0].upgrade == 2


async def test_upgrade_rejects_stale_level_missing_materials_and_other_owner(services, db):
    p, q = await reg(services), await reg(services, 11, "سارا")
    gid = (await services.inventory.view(p.id)).gear[0].id
    await fund(services, db, p.id, 5_000)
    with pytest.raises(GameError, match="مواد"):
        await services.shop.upgrade(p, gid, 1)
    assert (await services.players.require(10)).gold == p.gold + 5_000  # nothing was charged
    with pytest.raises(GameError):
        await services.shop.upgrade(p, gid, 3)  # stale confirmation button
    with pytest.raises(GameError):
        await services.shop.upgrade(q, gid, 1)  # not the owner


def test_upgrade_chances_never_increase():
    assert list(UPGRADE_CHANCE) == sorted(UPGRADE_CHANCE, reverse=True)


async def test_shop_commands_in_group(h, services, db):
    p = await reg(services)
    await h.say(10, "فروشگاه", group=True)
    assert "معجون انرژی" in h.session.last_text()
    await h.say(10, "خرید معجون انرژی 2", group=True)
    assert "اکنون در اختیار" in h.session.last_text()
    await h.say(10, "فروش معجون انرژی 2", group=True)
    assert "فروختید" in h.session.last_text()
    await h.say(10, "خرید چیزی که نیست", group=True)
    assert "پیدا نشد" in h.session.last_text()

    gid = (await services.inventory.view(p.id)).gear[0].id
    await fund(services, db, p.id, 5_000)
    await give(services, db, p.id, "iron_ore", 3)
    await h.say(10, f"ارتقا {gid}", group=True)
    assert "شانس موفقیت" in h.session.last_text()
    await h.click(10, h.button_data("ارتقا به"), group=True)
    assert "ارتقا" in h.session.last_text()

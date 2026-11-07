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


async def setup_pair(services, db):
    seller = await services.players.register(10, "a", "آرش", "elf", "archer")
    buyer = await services.players.register(11, "b", "سارا", "fairy", "mage")
    async with db.transaction() as tx:
        await wallet.apply(tx, buyer.id, gold=5_000, reason="test", now=services.ctx.now())
        await services.inventory.grant(tx, seller.id, "iron_sword")
        await services.inventory.grant(tx, seller.id, "iron_ore", 10)
    return await services.players.require(10), await services.players.require(11)


async def total_gold(services):
    return (await services.players.require(10)).gold + (await services.players.require(11)).gold


async def test_gear_sale_moves_item_and_charges_fee(services, db):
    seller, buyer = await setup_pair(services, db)
    gear = next(p for p in (await services.inventory.view(seller.id)).gear if p.item.id == "iron_sword")
    listing = await services.market.list_gear(seller, gear.id, 1_000)
    assert all(p.id != gear.id for p in (await services.inventory.view(seller.id)).gear)  # in escrow

    before = await total_gold(services)
    await services.market.buy(buyer, listing.id)
    fee = max(1, 1_000 * services.ctx.balance.market_fee_percent // 100)
    assert await total_gold(services) == before - fee  # the fee leaves the economy
    assert (await services.players.require(10)).gold == seller.gold + 1_000 - fee
    assert any(p.id == gear.id for p in (await services.inventory.view(buyer.id)).gear)


async def test_stack_listing_and_cancel(services, db):
    seller, _ = await setup_pair(services, db)
    ore = get_item("iron_ore")
    listing = await services.market.list_stack(seller, ore, 4, 400)
    stacks = dict((i.id, q) for i, q in (await services.inventory.view(seller.id)).stacks)
    assert stacks["iron_ore"] == 6
    await services.market.cancel(seller, listing.id)
    stacks = dict((i.id, q) for i, q in (await services.inventory.view(seller.id)).stacks)
    assert stacks["iron_ore"] == 10
    with pytest.raises(GameError):
        await services.market.cancel(seller, listing.id)


async def test_cannot_double_buy_or_buy_own_or_without_money(services, db):
    seller, buyer = await setup_pair(services, db)
    listing = await services.market.list_stack(seller, get_item("iron_ore"), 2, 100)
    with pytest.raises(GameError):
        await services.market.buy(seller, listing.id)
    poor = await services.players.register(12, "c", "رها", "dwarf", "guardian")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET gold = 0 WHERE id = ?", (poor.id,))
    with pytest.raises(wallet.InsufficientFunds):
        await services.market.buy(await services.players.require(12), listing.id)
    await services.market.buy(buyer, listing.id)
    with pytest.raises(GameError):
        await services.market.buy(buyer, listing.id)
    # the failed purchase did not strand anything: ore went to the first real buyer only
    stacks = dict((i.id, q) for i, q in (await services.inventory.view(buyer.id)).stacks)
    assert stacks["iron_ore"] == 2


async def test_listing_rules(services, db):
    seller, _ = await setup_pair(services, db)
    worn = (await services.inventory.view(seller.id)).gear[0]
    with pytest.raises(GameError):
        await services.market.list_gear(seller, worn.id, 100)  # equipped
    with pytest.raises(GameError):
        await services.market.list_stack(seller, get_item("iron_ore"), 99, 100)  # not enough
    with pytest.raises(GameError):
        await services.market.list_stack(seller, get_item("iron_ore"), 1, 0)
    with pytest.raises(GameError):
        await services.market.list_stack(seller, get_item("iron_ore"), 1, 10**9)


async def test_listed_gear_cannot_be_equipped_or_sold_to_npc(services, db):
    seller, _ = await setup_pair(services, db)
    gear = next(p for p in (await services.inventory.view(seller.id)).gear if p.item.id == "iron_sword")
    await services.market.list_gear(seller, gear.id, 500)
    with pytest.raises(GameError):
        await services.shop.sell_gear(seller, gear.id)
    with pytest.raises(GameError):
        await services.inventory.equip(seller, gear.id)


async def test_market_commands(h, services, db):
    seller, buyer = await setup_pair(services, db)
    gear = next(p for p in (await services.inventory.view(seller.id)).gear if p.item.id == "iron_sword")
    await h.say(10, f"عرضه #{gear.id} 1000", group=True)
    assert "آگهی" in h.session.last_text()
    await h.say(10, "عرضه سنگ آهن 3 90", group=True)
    assert "آگهی" in h.session.last_text()
    await h.say(11, "بازار", group=True)
    assert "شمشیر آهنی" in h.session.last_text() and "سنگ آهن" in h.session.last_text()
    await h.say(11, "بخر 1", group=True)
    assert "معامله مبارک" in h.session.last_text()
    await h.say(10, "لغو 2", group=True)
    assert "پس گرفتید" in h.session.last_text()

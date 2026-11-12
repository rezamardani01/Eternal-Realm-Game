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
        await services.inventory.grant(tx, seller.id, "iron_ore", 10)
    return await services.players.require(10), await services.players.require(11)


async def total_gold(services):
    return (await services.players.require(10)).gold + (await services.players.require(11)).gold


async def test_sale_moves_item_and_charges_fee(services, db):
    seller, buyer = await setup_pair(services, db)
    listing = await services.market.list_stack(seller, get_item("iron_ore"), 4, 400)
    assert (await services.inventory.view(seller.id)).stack_qty("iron_ore") == 6  # in escrow

    before = await total_gold(services)
    await services.market.buy(buyer, listing.id)
    fee = max(1, 400 * services.ctx.balance.market_fee_percent // 100)
    assert await total_gold(services) == before - fee  # the fee leaves the economy
    assert (await services.players.require(10)).gold == seller.gold + 400 - fee
    assert (await services.inventory.view(buyer.id)).stack_qty("iron_ore") == 4


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
    with pytest.raises(GameError):
        await services.market.list_stack(seller, get_item("iron_ore"), 99, 100)  # not enough
    with pytest.raises(GameError):
        await services.market.list_stack(seller, get_item("iron_ore"), 1, 0)
    with pytest.raises(GameError):
        await services.market.list_stack(seller, get_item("iron_ore"), 1, 10**9)


async def test_a_listing_may_ask_between_half_and_one_and_a_fifth_of_the_real_worth(services, db):
    from eternal_realm.game.data.items import item_value

    seller, _ = await setup_pair(services, db)
    ore = get_item("iron_ore")
    worth = item_value(ore) * 4
    low, high = services.market.price_range(ore, 4)
    assert (low, high) == (-(-worth // 2), worth * 120 // 100)
    for bad in (low - 1, high + 1, 48_999):
        with pytest.raises(GameError, match="باید میان"):
            await services.market.list_stack(seller, ore, 2, bad) if False else await services.market.list_stack(seller, ore, 4, bad)
    await services.market.list_stack(seller, ore, 4, low)
    await services.market.list_stack(seller, ore, 4, high)
    # a cheap item can never be listed for a fortune
    assert services.market.price_range(get_item("herb"))[1] < 100

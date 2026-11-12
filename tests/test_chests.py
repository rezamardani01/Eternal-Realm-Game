import random

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.chests import CHESTS
from eternal_realm.game.data.items import ITEMS, get_item
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def reg(services, db, gold=0, crystal=0):
    p = await services.players.register(10, "a", "آرش", "elf", "archer")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, crystal=crystal, reason="test", now=services.ctx.now())
    return await services.players.require(10)


def test_every_prize_references_a_real_item_and_odds_sum_to_one(services):
    for chest in CHESTS.values():
        assert chest.item_id in ITEMS
        assert abs(sum(share for _, share in services.chests.odds(chest)) - 1) < 1e-9
        for prize in chest.prizes:
            assert prize.item_id is None or prize.item_id in ITEMS
            assert prize.weight > 0


def test_empirical_odds_match_the_published_ones(services):
    chest = CHESTS["magic_chest"]
    services.ctx.rng = random.Random(99)
    n = 20_000
    rolls = [services.chests.roll(chest) for _ in range(n)]
    for prize, share in services.chests.odds(chest):
        observed = rolls.count(prize) / n
        assert abs(observed - share) < 0.015


async def test_buy_and_open_chest_with_crystals(services, db):
    p = await reg(services, db, crystal=100)
    currency, total = await services.chests.buy(p, "magic_chest", 2)
    assert (currency, total) == ("crystal", 60)
    assert (await services.players.require(10)).crystal == 40
    opened = await services.chests.open(p, get_item("magic_chest"))
    assert opened.prize in CHESTS["magic_chest"].prizes
    left = {i.id: q for i, q in (await services.inventory.view(p.id)).stacks}
    assert left["magic_chest"] == 1


async def test_cannot_buy_without_funds_or_open_without_chest(services, db):
    p = await reg(services, db, gold=100)
    with pytest.raises(wallet.InsufficientFunds):
        await services.chests.buy(p, "royal_chest")
    with pytest.raises(GameError):
        await services.chests.open(p, get_item("wooden_chest"))
    assert (await services.players.require(10)).crystal == 0


async def test_chest_rewards_are_all_credited(services, db):
    p = await reg(services, db, gold=600 * 30)
    await services.chests.buy(p, "wooden_chest", 20)
    before = await services.players.require(10)
    for _ in range(20):
        await services.chests.open(p, get_item("wooden_chest"))
    after = await services.players.require(10)
    assert after.gold >= before.gold and after.crystal >= before.crystal
    assert not {i.id: q for i, q in (await services.inventory.view(p.id)).stacks}.get("wooden_chest")


async def test_open_all_opens_every_chest_in_one_go_and_sums_the_prizes(services, db):
    from eternal_realm.game.data.items import get_item
    from eternal_realm.game.services.chests import OPEN_ALL_LIMIT

    p = await services.players.register(10, "u", "آرش", "elf", "archer")
    async with db.transaction() as tx:
        await services.inventory.grant(tx, p.id, "wooden_chest", 40)
        await services.inventory.grant(tx, p.id, "magic_chest", 3)
    before = await services.players.require(10)
    total = await services.chests.open_all(before)
    assert total.count == 43 and total.chests == {"wooden_chest": 40, "magic_chest": 3}
    view = await services.inventory.view(p.id)
    assert view.stack_qty("wooden_chest") == 0 and view.stack_qty("magic_chest") == 0
    after = await services.players.require(10)
    assert after.gold - before.gold == total.gold and after.crystal - before.crystal == total.crystal
    for item_id, qty in total.items.items():  # the sum matches what really landed in the backpack
        assert view.stack_qty(item_id) >= qty
    with pytest.raises(GameError):
        await services.chests.open_all(after)  # nothing left to open

    async with db.transaction() as tx:
        await services.inventory.grant(tx, p.id, "wooden_chest", OPEN_ALL_LIMIT + 5)
        await services.inventory.grant(tx, p.id, "magic_chest", 2)
    only = await services.chests.open_all(await services.players.require(10), get_item("magic_chest"))
    assert only.chests == {"magic_chest": 2}  # one kind only, when asked
    big = await services.chests.open_all(await services.players.require(10))
    assert big.count == OPEN_ALL_LIMIT  # a single tap is bounded; the rest stays for the next tap
    assert (await services.inventory.view(p.id)).stack_qty("wooden_chest") == 5


async def test_the_chest_screens_offer_open_all(h, services, db):
    p = await services.players.register(10, "u", "آرش", "elf", "archer")
    async with db.transaction() as tx:
        await services.inventory.grant(tx, p.id, "wooden_chest", 40)
    await h.say(10, "/start")
    await h.panel(10, "chests")
    assert any("باز کردن همه‌ی صندوقچه‌ها" in t and "۴۰" in t for t in h.labels())
    await h.panel(10, "item", "wooden_chest")
    assert any("باز کردن همه" in t for t in h.labels())
    await h.panel(10, "openall")
    assert "۴۰ صندوقچه باز شد" in h.session.last_text()
    assert (await services.inventory.view(p.id)).stack_qty("wooden_chest") == 0
    await h.panel(10, "chests")
    assert not any("باز کردن همه" in t for t in h.labels())  # nothing left, so no button

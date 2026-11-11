"""Many simultaneous requests must neither deadlock nor duplicate money or items."""

import asyncio

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.items import get_item
from eternal_realm.game.engine.combat import Action
from eternal_realm.shared.errors import GameError


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


async def test_hundreds_of_players_acting_at_once(services):
    players = [
        await services.players.register(1000 + i, f"u{i}", f"بازیکن{i}", "elf", "archer") for i in range(60)
    ]
    results = await asyncio.wait_for(
        asyncio.gather(
            *(services.activities.perform(p.id, a) for p in players for a in ("fishing", "mining", "herb")),
            return_exceptions=True,
        ),
        timeout=30,
    )
    assert not [r for r in results if isinstance(r, Exception) and not isinstance(r, GameError)]
    for p in players:
        after = await services.players.require(p.platform_user_id)
        assert after.energy >= 0 and after.gold >= 0


async def test_same_action_spammed_by_one_player_charges_energy_once(services):
    p = await services.players.register(10, "u", "آرش", "elf", "archer")
    results = await asyncio.gather(*(services.activities.perform(p.id, "fishing") for _ in range(20)), return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1  # the cooldown admits exactly one
    assert (await services.players.require(10)).energy == p.energy - 5


async def test_two_buyers_racing_for_one_listing(services, db):
    seller = await services.players.register(10, "a", "فروشنده", "elf", "archer")
    buyers = [await services.players.register(20 + i, "b", f"خریدار{i}", "elf", "archer") for i in range(5)]
    async with db.transaction() as tx:
        await services.inventory.grant(tx, seller.id, "iron_ore", 3)
        for b in buyers:
            await wallet.apply(tx, b.id, gold=1_000, reason="t", now=services.ctx.now())
    listing = await services.market.list_stack(await services.players.require(10), get_item("iron_ore"), 3, 300)
    results = await asyncio.gather(*(services.market.buy(b, listing.id) for b in buyers), return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1
    holders = 0
    for b in buyers:
        stacks = {i.id: q for i, q in (await services.inventory.view(b.id)).stacks}
        holders += stacks.get("iron_ore", 0)
    assert holders == 3  # the ore exists exactly once


async def test_duel_actions_racing_do_not_double_pay(services):
    a = await services.players.register(10, "a", "آرش", "dragonborn", "warrior")
    b = await services.players.register(11, "b", "سارا", "fairy", "mage")
    duel = await services.duels.challenge(-1, a, b)
    update = await services.duels.accept(duel.id, b)
    actor = a if update.battle.current.player_id == a.id else b
    results = await asyncio.gather(
        *(services.duels.act(duel.id, actor, Action.SURRENDER) for _ in range(6)), return_exceptions=True
    )
    assert sum(not isinstance(r, Exception) for r in results) == 1
    async with services.ctx.db.read() as tx:
        paid = await tx.scalar("SELECT COUNT(*) FROM transactions WHERE reason = 'duel_win'", default=0)
    assert paid <= 1

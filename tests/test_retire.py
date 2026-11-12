"""The retirement of the old gear system, and proof that nothing of it is left in the game."""

import json

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.items import ITEMS, Kind
from eternal_realm.game.services.retire import LEGACY_VALUE, retire_old_gear

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


async def hero(services, uid=10, name="آرش"):
    return await services.players.register(uid, f"u{uid}", name, "elf", "archer")


async def old_piece(db, player_id, item_id, upgrade=0, slot=None):
    async with db.transaction() as tx:
        return await tx.execute(
            "INSERT INTO gear (player_id, item_id, upgrade, slot, created_at) VALUES (?, ?, ?, ?, 0)",
            (player_id, item_id, upgrade, slot),
        )


async def test_old_gear_turns_into_coins_once(services, db):
    a, b = await hero(services), await hero(services, 11, "سارا")
    await old_piece(db, a.id, "steel_sword", upgrade=2, slot="weapon")
    await old_piece(db, a.id, "leather_cap")
    await old_piece(db, b.id, "dragon_armor")
    gold_a = (await services.players.require(10)).gold
    paid = await retire_old_gear(db, services.ctx.now())
    assert paid[a.id] == (2, round(3200 * 2) + 120) and paid[b.id] == (1, 40_000)
    assert (await services.players.require(10)).gold == gold_a + paid[a.id][1]
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM gear", (), 0) == 0
    assert await retire_old_gear(db, services.ctx.now()) == {}  # nothing is paid twice
    assert (await services.players.require(10)).gold == gold_a + paid[a.id][1]


async def test_listings_and_bets_over_old_gear_are_closed(services, db):
    a = await hero(services)
    gid = await old_piece(db, a.id, "iron_sword")
    async with db.transaction() as tx:
        await tx.execute(
            "INSERT INTO market_listings (seller_id, item_id, qty, gear_id, price, status, created_at)"
            " VALUES (?, 'iron_sword', 1, ?, 500, 'active', 0)", (a.id, gid),
        )
        await tx.execute(
            "INSERT INTO bet_duels (chat_id, challenger_id, kind, item_id, amount, status, created_at, expires_at, gear_id)"
            " VALUES (1, ?, 'gear', 'iron_sword', 1, 'open', 0, 99, ?)", (a.id, gid),
        )
    await retire_old_gear(db, services.ctx.now())
    async with db.read() as tx:
        assert await tx.scalar("SELECT status FROM market_listings", (), "") == "cancelled"
        assert await tx.scalar("SELECT status FROM bet_duels", (), "") == "cancelled"


async def test_fights_of_the_old_engine_are_closed_and_new_ones_kept(services, db):
    a = await hero(services)
    async with db.transaction() as tx:
        for state in ('{"fighters": []}', json.dumps({"fighters": [{"cds": [0, 0, 0]}]})):
            await tx.execute(
                "INSERT INTO solo_fights (player_id, kind, status, state, info, created_at, updated_at)"
                " VALUES (?, 'arena', 'active', ?, '{}', 0, 0)", (a.id, state),
            )
    await retire_old_gear(db, services.ctx.now())
    async with db.read() as tx:
        rows = await tx.fetchall("SELECT status, state FROM solo_fights ORDER BY id")
    assert [r["status"] for r in rows] == ["fled", "active"]


def test_nothing_of_the_old_gear_is_left_in_the_catalogue():
    assert {i.kind for i in ITEMS.values()} <= {Kind.CONSUMABLE, Kind.MATERIAL, Kind.CHEST}
    assert not set(LEGACY_VALUE) & set(ITEMS)  # every old id is gone from the game
    from eternal_realm.game.data.chests import CHESTS
    from eternal_realm.game.data.lucky import THEMES
    from eternal_realm.game.data.wheel import SLICES

    for chest in CHESTS.values():
        assert all(p.item_id in ITEMS for p in chest.prizes if p.item_id)
    assert all(p.item_id in ITEMS for t in THEMES for p in t.prizes if p.item_id)
    assert all(i in ITEMS for s in SLICES for i, _ in s.items)


async def test_old_screens_and_words_are_gone(services, db):
    h = Harness(services)
    await hero(services)
    await h.say(10, "/start")
    for old in ("gear", "piece", "equip", "craft", "betgear", "up", "upq", "sellq"):
        h.session.reset()
        await h.panel(10, old, "1")
        assert not h.session.texts() or "نیست" in " ".join(h.session.texts()) or h.session.callback_answers(), old
    from eternal_realm.bot.commands import REGISTRY

    assert REGISTRY.resolve("کوره") is None and REGISTRY.resolve("آهنگری") is None
    assert REGISTRY.resolve("تجهیزات") is not None  # it now opens the war-gear screen
    await h.say(10, "تجهیزات")
    assert "تجهیزات قهرمان" in h.session.last_text()

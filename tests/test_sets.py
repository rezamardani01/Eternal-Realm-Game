import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import inventory as inv_repo
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.sets import BOSS_DROPS, SETS, set_bonus
from eternal_realm.game.data.items import get_item

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=30, gold=50_000):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


def test_every_set_piece_and_drop_exists():
    for gear_set in SETS:
        for piece in gear_set.pieces:
            assert get_item(piece).is_gear
    assert all(get_item(i).is_gear for i, _ in BOSS_DROPS)


def test_set_bonus_grows_with_pieces():
    assert set_bonus(["iron_sword"]).defense == 0
    two = set_bonus(["iron_sword", "iron_shield"])
    three = set_bonus(["iron_sword", "iron_shield", "iron_helm"])
    assert two.defense == 3 and three.defense == 3 and three.atk == 5 and three.hp == 25


async def test_wearing_a_set_changes_equipped_stats(services, db):
    p = await hero(services, db, 1, "آرش")
    async with db.transaction() as tx:
        base = await services.inventory.equipped_stats(tx, p.id)
        ids = [(await services.inventory.grant(tx, p.id, i))[0] for i in ("leather_cap", "leather_armor")]
    for gid in ids:
        await services.inventory.equip(await services.players.require(1), gid)
    async with db.transaction() as tx:
        worn = await services.inventory.equipped_stats(tx, p.id)
    plain = get_item("leather_cap").stats + get_item("leather_armor").stats
    assert worn.speed == base.speed + plain.speed + 3  # the 2-piece bonus
    lines = await services.inventory.set_lines(p.id, "leather_cap")
    assert "۲ از ۳" in lines[0] and lines[1].startswith("✅") and any(line.startswith("🔒") for line in lines)


async def test_history_follows_a_traded_piece(h, services, db):
    seller, buyer = await hero(services, db, 1, "آرش"), await hero(services, db, 2, "سارا")
    async with db.transaction() as tx:
        gid = (await services.inventory.grant(tx, seller.id, "steel_sword", 1, origin="غنیمت شکست باس\nنخستین صاحب: آرش"))[0]
    listing = await services.market.list_gear(seller, gid, 500)
    await services.market.buy(buyer, listing.id)
    async with db.read() as tx:
        row = await inv_repo.get_gear(tx, gid)
    assert row.player_id == buyer.id
    assert row.origin.splitlines() == ["غنیمت شکست باس", "نخستین صاحب: آرش", "دست‌به‌دست شد؛ صاحب قبلی: آرش"]

    await h.say(2, "تجهیزات", group=True)
    await h.panel(2, "piece", str(gid), group=True)
    text = h.session.sent("editMessageText")[-1]["text"]
    assert "تاریخچه" in text and "صاحب قبلی: آرش" in text


async def test_defeating_a_boss_can_drop_a_trophy_with_history(services, db, clock):
    from tests.test_boss import advance_until_ended, edit_state, squad

    players, view = await squad(services, db, 4)
    await services.bosses.start(view.id, players[0])
    await edit_state(db, view.id, lambda s: s["boss"].update(hp=100, max_hp=100, atk=1))
    services.ctx.rng.seed(3)
    updates = await advance_until_ended(services, clock)
    final = next(u for u in updates if u.kind == "final").view
    dropped = [p for p in final.payouts if p.trophy]
    async with db.read() as tx:
        rows = await tx.fetchall("SELECT origin FROM gear WHERE origin LIKE 'غنیمت شکست%'")
    assert len(rows) == len(dropped)
    if dropped:
        assert "نخستین صاحب" in rows[0]["origin"]


async def test_weapon_bond_grows_with_use_and_adds_stats(services, db):
    from eternal_realm.db.repos import inventory as inv_repo
    from eternal_realm.game.data.sets import BOND_STEPS, bond_level

    assert [bond_level(n) for n in (0, 24, 25, 75, 150, 999)] == [0, 0, 1, 2, 3, 3]
    p = await hero(services, db, 30, "آرش")
    async with db.transaction() as tx:
        gid = (await services.inventory.grant(tx, p.id, "steel_sword"))[0]
    await services.inventory.equip(await services.players.require(30), gid)
    async with db.transaction() as tx:
        base = await services.inventory.equipped_stats(tx, p.id)
        await inv_repo.add_bond(tx, p.id, BOND_STEPS[0])
        bonded = await services.inventory.equipped_stats(tx, p.id)
    assert bonded.atk > base.atk
    async with db.transaction() as tx:
        await inv_repo.add_bond(tx, p.id, 200)
        piece = await services.inventory.piece(tx, p.id, gid)
    assert piece.bond == 3 and piece.bond_uses == BOND_STEPS[0] + 200
    shown = await services.inventory.view(p.id)
    assert next(x for x in shown.gear if x.id == gid).bond == 3


async def test_armor_never_bonds(services, db):
    from eternal_realm.db.repos import inventory as inv_repo

    p = await hero(services, db, 31, "سارا")
    async with db.transaction() as tx:
        gid = (await services.inventory.grant(tx, p.id, "chain_mail"))[0]
        await inv_repo.add_bond(tx, p.id, 500)
        piece = await services.inventory.piece(tx, p.id, gid)
    assert piece.bond == 0

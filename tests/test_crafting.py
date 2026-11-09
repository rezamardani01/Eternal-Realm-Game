import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data.items import get_item
from eternal_realm.game.data.recipes import RECIPES
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, stock=None, gold=10_000):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await wallet.apply(tx, p.id, gold=gold, reason="t", now=services.ctx.now())
        for item_id, qty in (stock or {}).items():
            await services.inventory.grant(tx, p.id, item_id, qty)
    return await services.players.require(uid)


def test_recipes_are_valid():
    for r in RECIPES:
        assert get_item(r.result).is_gear and (not r.base or get_item(r.base).is_gear)
        assert all(get_item(i) for i in r.materials)


async def test_craft_uses_the_base_materials_and_gold(services, db):
    recipe = RECIPES[0]
    stock = {recipe.base: 1, **recipe.materials}
    p = await hero(services, db, 1, "آرش", stock)
    view = await services.crafting.view(p, recipe.id)
    assert view.ready
    gold = p.gold
    made = await services.crafting.craft(p, recipe.id)
    assert made.id == recipe.result
    after = await services.inventory.view(p.id)
    ids = [g.item.id for g in after.gear]
    assert recipe.result in ids and recipe.base not in ids  # the base piece was consumed
    assert all(q == 0 or i.id not in recipe.materials for i, q in after.stacks)
    assert (await services.players.require(1)).gold == gold - recipe.gold
    with pytest.raises(GameError, match="از قبل"):
        await services.crafting.craft(p, recipe.id)


async def test_missing_materials_rolls_everything_back(services, db):
    recipe = RECIPES[0]
    stock = {recipe.base: 1}
    p = await hero(services, db, 2, "سارا", stock)
    view = await services.crafting.view(p, recipe.id)
    assert not view.ready
    with pytest.raises(GameError):
        await services.crafting.craft(p, recipe.id)
    gear = [g.item.id for g in (await services.inventory.view(p.id)).gear]
    assert recipe.base in gear and (await services.players.require(2)).gold == p.gold


async def test_worn_base_piece_is_not_used(services, db):
    recipe = RECIPES[0]
    p = await hero(services, db, 3, "رها", {recipe.base: 1, **recipe.materials})
    piece = next(g for g in (await services.inventory.view(p.id)).gear if g.item.id == recipe.base)
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 20 WHERE id = ?", (p.id,))
    await services.inventory.equip(await services.players.require(3), piece.id)
    with pytest.raises(GameError, match="آزاد"):
        await services.crafting.craft(p, recipe.id)


async def test_glass_flow(h, services, db):
    recipe = RECIPES[4]
    await hero(services, db, 4, "نگار", {recipe.base: 1, **recipe.materials})
    await h.say(4, "کوره")
    await h.click(4, h.button_data("اژدهاکش"))
    assert "نیازمندی" in h.session.sent("editMessageText")[-1]["text"]
    await h.tap(4, "بله، بساز")
    assert "ساخته شد" in h.session.sent("editMessageText")[-1]["text"]

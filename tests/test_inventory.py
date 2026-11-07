import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.items import get_item
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def reg(services, uid=10, name="آرش", race="elf", cls="archer"):
    return await services.players.register(uid, "u", name, race, cls)


async def test_starter_kit_is_equipped(services):
    p = await reg(services)
    view = await services.inventory.view(p.id)
    assert [pc.item.id for pc in view.gear] == ["short_bow"] and view.gear[0].slot == "weapon"
    assert {i.id: q for i, q in view.stacks} == {"energy_potion": 2}
    stats = await services.characters.stats(p)
    assert stats.atk >= 3 + 10  # base attack plus the bow


async def test_equip_swaps_pieces_and_respects_level(services, db):
    p = await reg(services)
    async with db.transaction() as tx:
        cheap = (await services.inventory.grant(tx, p.id, "dagger"))[0]
        iron = (await services.inventory.grant(tx, p.id, "iron_sword"))[0]
    _, replaced = await services.inventory.equip(p, cheap)
    assert replaced is not None and replaced.item.id == "short_bow"
    with pytest.raises(GameError):
        await services.inventory.equip(p, iron)  # needs level 5
    with pytest.raises(GameError):
        await services.inventory.equip(p, cheap)  # already worn


async def test_cannot_touch_someone_elses_gear(services):
    a, b = await reg(services), await reg(services, 11, "سارا", "fairy", "mage")
    gid = (await services.inventory.view(b.id)).gear[0].id
    with pytest.raises(GameError):
        await services.inventory.equip(a, gid)


async def test_use_energy_potion(services, db):
    p = await reg(services)
    async with db.transaction() as tx:
        await services.players.spend_energy(tx, p.id, 60)
    await services.inventory.use(p, get_item("energy_potion"))
    assert (await services.players.require(10)).energy == 80


async def test_potion_not_wasted_at_full_energy(services):
    p = await reg(services)
    with pytest.raises(GameError):
        await services.inventory.use(p, get_item("energy_potion"))
    view = await services.inventory.view(p.id)
    assert {i.id: q for i, q in view.stacks}["energy_potion"] == 2


async def test_inventory_commands_in_group(h, services):
    await reg(services)
    await h.say(10, "کوله‌پشتی", group=True)
    assert "کمان کوتاه" in h.session.last_text() and "معجون انرژی" in h.session.last_text()
    await h.say(10, "تجهیزات", group=True)
    assert "سلاح" in h.session.last_text()
    await h.say(10, "مصرف معجون انرژی", group=True)
    assert "انرژی‌ات پر است" in h.session.last_text()

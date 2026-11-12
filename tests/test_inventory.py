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


async def test_starter_kit_is_just_potions(services):
    p = await reg(services)
    view = await services.inventory.view(p.id)
    assert {i.id: q for i, q in view.stacks} == {"energy_potion": 2}
    assert not await services.arms.owned(p.id)  # no gear to start with: war gear is found or bought


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

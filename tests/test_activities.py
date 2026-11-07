import random

import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.activities import ACTIVITIES, FISHING
from eternal_realm.game.engine import loot
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


def test_loot_distribution_is_sane():
    rng = random.Random(7)
    results = [loot.roll(FISHING, 1, 5, 1.0, rng) for _ in range(5000)]
    assert all(r.gold >= 0 and r.xp >= 0 for r in results)
    crystals = sum(r.crystal for r in results)
    assert crystals < 5000 * 0.02  # crystals stay rare
    assert any(r.items.get("golden_fish") for r in results)


def test_luck_makes_rare_outcomes_likelier():
    def rare_rate(luck):
        rng = random.Random(3)
        return sum(loot.roll(FISHING, 1, luck, 1.0, rng).outcome.rare for _ in range(8000))

    assert rare_rate(80) > rare_rate(0)


def test_levels_never_gate_out_all_outcomes():
    rng = random.Random(1)
    for activity in ACTIVITIES.values():
        for level in (1, 10, 50):
            assert loot.roll(activity, level, 0, 1.0, rng).outcome in activity.outcomes


async def test_fishing_spends_energy_gives_rewards_and_sets_cooldown(services, clock):
    p = await reg(services)
    result = await services.activities.perform(p.id, "fishing")
    assert result.player.energy == p.energy - FISHING.energy
    after = await services.players.require(10)
    assert after.gold >= p.gold and after.xp + (after.level - 1) * 100 >= 0
    with pytest.raises(GameError) as err:
        await services.activities.perform(p.id, "fishing")
    assert "دیگر" in err.value.message
    clock.advance(FISHING.cooldown + 1)
    await services.activities.perform(p.id, "fishing")


async def test_not_enough_energy_changes_nothing(services, clock, db):
    p = await reg(services)
    async with db.transaction() as tx:
        await services.players.spend_energy(tx, p.id, 98)
    with pytest.raises(GameError):
        await services.activities.perform(p.id, "fishing")
    after = await services.players.require(10)
    assert after.energy == 2 and after.gold == p.gold and after.xp == 0
    # the failed attempt must not have started a cooldown either
    clock.advance(1)
    async with db.transaction() as tx:
        await services.players.add_energy(tx, p.id, 50)
    await services.activities.perform(p.id, "fishing")


async def test_fishing_command_in_group(h, services):
    await reg(services)
    await h.say(10, "ماهیگیری", group=True)
    text = h.session.last_text()
    assert "قلابش" in text and "انرژی" in text
    await h.say(10, "ماهی", group=True)  # alias, but still on cooldown
    assert "خسته" in h.session.last_text()


async def test_group_can_disable_activity(h, services):
    await reg(services)
    await h.say(10, "راهنما", group=True)  # registers the group
    await services.groups.set_command(-500, "fishing", False)
    await h.say(10, "ماهیگیری", group=True)
    assert "غیرفعال" in h.session.last_text()


@pytest.mark.parametrize("word", ["معدن", "گیاه", "جستجو"])
async def test_each_activity_command_works(h, services, word):
    await reg(services)
    await h.say(10, word, group=True)
    assert "انرژی" in h.session.last_text()


def test_race_perk_boosts_matching_activity():
    from eternal_realm.game.data.activities import MINING

    def total_ore(perk):
        rng = random.Random(11)
        return sum(
            loot.roll(MINING, 10, 0, perk, rng).items.get("iron_ore", 0) for _ in range(3000)
        )

    assert total_ore(1.3) > total_ore(1.0) * 1.15


async def test_rest_restores_energy_once_per_cooldown(h, services, db, clock):
    p = await reg(services)
    await h.say(10, "استراحت", group=True)
    assert "پر است" in h.session.last_text()
    async with db.transaction() as tx:
        await services.players.spend_energy(tx, p.id, 60)
    await h.say(10, "استراحت", group=True)
    assert "۲۵" in h.session.last_text()
    await h.say(10, "استراحت", group=True)
    assert "دیگر" in h.session.last_text()
    clock.advance(1801)  # natural regeneration also tops the bar up, so only part of 25 fits
    await h.say(10, "استراحت", group=True)
    assert "انرژی گرفت" in h.session.last_text()

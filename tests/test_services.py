import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.packs import PACKS
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, tickets=()):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        for t in tickets:
            await services.inventory.grant(tx, p.id, t, 1)
    return await services.players.require(uid)


def test_ticket_packs_deliver_a_ticket():
    for pack_id, ticket in (("svc_rename", "rename_ticket"), ("svc_race", "race_ticket"), ("svc_class", "class_ticket")):
        assert PACKS[pack_id].items == {ticket: 1}


async def test_race_and_class_change_consume_a_ticket(services, db):
    p = await hero(services, db, 1, "آرش", ["race_ticket", "class_ticket"])
    p = await services.characters.change_race(p, "dwarf")
    assert p.race_id == "dwarf"
    with pytest.raises(GameError):  # the ticket is gone
        await services.characters.change_race(p, "elf")
    p = await services.characters.change_class(p, "mage")
    assert p.class_id == "mage"


async def test_without_a_ticket_nothing_changes(services, db):
    p = await hero(services, db, 2, "سارا")
    with pytest.raises(GameError):
        await services.characters.change_class(p, "mage")
    assert (await services.players.require(2)).class_id == "warrior"


async def test_changing_class_clears_a_clashing_second_class(services, db):
    p = await hero(services, db, 3, "رها", ["class_ticket"])
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET class2 = 'mage' WHERE id = ?", (p.id,))
    p = await services.characters.change_class(await services.players.require(3), "mage")
    assert p.class_id == "mage" and p.class2_id == ""


async def test_rename_needs_a_ticket_a_free_name_and_confirmation(h, services, db):
    await hero(services, db, 4, "نگار")
    await hero(services, db, 5, "گرفته")
    await h.say(4, "تغییر نام تازه نام")
    assert "برگه‌ی تغییر نام" in h.session.sent()[-1]["text"]
    pid = (await services.players.require(4)).id
    async with db.transaction() as tx:
        await services.inventory.grant(tx, pid, "rename_ticket", 1)
    await h.say(4, "تغییر نام گرفته")
    await h.tap(4, "بله، عوض کن")
    assert (await services.players.require(4)).name == "نگار"  # taken: refused, ticket kept
    await h.say(4, "تغییر نام ماه تابان")
    assert "تأیید تغییر نام" in h.session.sent()[-1]["text"] and (await services.players.require(4)).name == "نگار"
    await h.tap(4, "بله، عوض کن")
    assert (await services.players.require(4)).name == "ماه تابان"

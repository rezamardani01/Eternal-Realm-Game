import pytest

from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.game.data.quests import QUESTS
from eternal_realm.shared.errors import GameError

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=1), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid, name, level=5):
    p = await services.players.register(uid, f"u{uid}", name, "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ? WHERE id = ?", (level, p.id))
    return await services.players.require(uid)


def test_every_story_is_consistent():
    for quest in QUESTS:
        assert "start" in quest.steps
        for step_id, step in quest.steps.items():
            assert bool(step.choices) != bool(step.reward), f"{quest.id}/{step_id} must be a scene or an ending"
            for choice in step.choices:
                assert choice.next in quest.steps


async def test_choices_decide_the_ending_and_pay_once(services, db):
    p = await hero(services, db, 1, "آرش")
    before = p.gold
    view = await services.quests.choose(p, "lost_letter", 0)  # deliver
    assert view.step_id == "deliver" and not view.done
    view = await services.quests.choose(p, "lost_letter", 0)  # humble
    assert view.done and view.step.ending == "پایان مهربانانه" and view.reward.crystal == 2
    after = await services.players.require(1)
    assert after.gold == before + 200 and after.crystal >= 2
    with pytest.raises(GameError, match="تا پایان"):
        await services.quests.choose(p, "lost_letter", 0)
    assert (await services.players.require(1)).gold == before + 200


async def test_locked_choice_and_level_gate(services, db):
    low = await hero(services, db, 2, "سارا", level=1)
    with pytest.raises(GameError, match="سطح"):
        await services.quests.view(low, "mist_gate")
    p = await hero(services, db, 3, "رها", level=5)
    await services.quests.choose(p, "mist_gate", 1)  # ask who he is: no lantern
    await services.quests.choose(p, "mist_gate", 1)  # wrong riddle answer
    view = await services.quests.view(p, "mist_gate")
    assert [c.next for _, c in view.options] == ["end_fight", "end_flee"]
    with pytest.raises(GameError, match="بسته"):
        await services.quests.choose(p, "mist_gate", 0)  # the lantern route needs the lantern


async def test_glass_flow(h, services, db):
    await hero(services, db, 4, "نگار")
    await h.say(4, "داستان", group=True)
    await h.click(4, h.button_data("نامه‌ی گمشده"), group=True)
    assert "کنار جاده" in h.session.sent("editMessageText")[-1]["text"]
    await h.click(4, h.button_data("نامه را به صاحبش"), group=True)
    await h.click(4, h.button_data("جایزه‌اش را قبول نمی‌کنم"), group=True)
    assert "پاداش شما" in h.session.sent("editMessageText")[-1]["text"]
    assert not [b for b in h.session.last_buttons() if "qgo" in b.get("callback_data", "")]

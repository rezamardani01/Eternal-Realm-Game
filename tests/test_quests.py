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


QUESTS_BY_ID = {q.id: q for q in QUESTS}


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
    await h.click(4, h.button_data("داستان‌های ویژه"), group=True)
    await h.click(4, h.button_data("نامه‌ی گمشده"), group=True)
    assert "کنار جاده" in h.session.sent("editMessageText")[-1]["text"]
    await h.click(4, h.button_data("نامه را به صاحبش"), group=True)
    await h.click(4, h.button_data("جایزه‌اش را قبول نمی‌کنم"), group=True)
    assert "پاداش شما" in h.session.sent("editMessageText")[-1]["text"]
    assert not [b for b in h.session.last_buttons() if "qgo" in b.get("callback_data", "")]


def test_a_hundred_generated_stories_in_ten_chapters():
    from eternal_realm.game.data.story_gen import CHAPTER_LEVELS

    generated = [q for q in QUESTS if q.chapter]
    assert len(generated) == 100 and len({q.id for q in generated}) == 100
    assert len({q.title for q in generated}) == 100  # every story has its own title
    for chapter in range(1, 11):
        stories = [q for q in generated if q.chapter == chapter]
        assert len(stories) == 10 and all(q.level_req == CHAPTER_LEVELS[chapter - 1] for q in stories)
    assert list(CHAPTER_LEVELS) == sorted(CHAPTER_LEVELS) and CHAPTER_LEVELS[0] == 1
    for q in generated:
        assert "{" not in q.title and all("{" not in step.text for step in q.steps.values())
        assert set(q.steps) == {"start", "mid_kind", "mid_clever", "mid_brave", "end_kind", "end_clever", "end_brave", "end_plain"}
    # later chapters pay more
    first, last = QUESTS_BY_ID["c1s1"].steps["end_kind"].reward, QUESTS_BY_ID["c10s1"].steps["end_kind"].reward
    assert last.gold > first.gold and last.xp > first.xp


async def test_chapters_open_with_the_players_level(h, services, db):
    p = await hero(services, db, 20, "نگار", level=1)
    await h.say(20, "داستان", group=True)
    assert any("فصل ۲" in t and "🔒" in t for t in h.labels())
    await h.click(20, h.button_data("فصل ۲"), group=True)
    assert "هنوز بسته است" in h.session.sent("editMessageText")[-1]["text"]
    with pytest.raises(GameError, match="سطح"):
        await services.quests.view(p, "c2s1")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = 6 WHERE id = ?", (p.id,))
    await h.say(20, "داستان", group=True)
    await h.click(20, h.button_data("فصل ۲"), group=True)
    assert "فصل ۲" in h.session.sent("editMessageText")[-1]["text"]
    assert len([b for b in h.session.last_buttons() if "quest:" in b.get("callback_data", "")]) == 10


async def test_a_generated_story_can_be_played_to_a_kind_ending(services, db):
    p = await hero(services, db, 21, "رها", level=1)
    before = await services.players.require(21)
    v = await services.quests.choose(p, "c1s1", 0)  # the kind way
    assert v.step_id == "mid_kind" and "kind" in v.flags
    v = await services.quests.choose(p, "c1s1", 0)
    assert v.done and v.step.ending == "پایان مهربانانه" and v.reward.crystal >= 1
    after = await services.players.require(21)
    assert after.gold > before.gold and after.crystal > before.crystal
    with pytest.raises(GameError, match="تا پایان"):
        await services.quests.choose(p, "c1s1", 0)


async def test_every_generated_story_is_playable_from_start_to_an_ending(services, db):
    from eternal_realm.game.data.story_gen import CHAPTER_LEVELS

    p = await hero(services, db, 22, "پویا", level=90)
    for q in [x for x in QUESTS if x.chapter]:
        for trait, index in (("kind", 0), ("clever", 1), ("brave", 2)):
            step, seen = "start", 0
            while q.steps[step].choices and seen < 6:
                options = q.steps[step].choices
                step = options[index if step == "start" else 0].next
                seen += 1
            assert q.steps[step].reward is not None, (q.id, trait)
    assert CHAPTER_LEVELS[-1] <= 90

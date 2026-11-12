"""The academy: lessons learned from what a hero really does, the notes it sends, the practice fight and the graduation."""

import pytest

from eternal_realm.bot.callbacks import ClassCb, RaceCb
from eternal_realm.bot.commands.registry import REGISTRY
from eternal_realm.bot.panel import SCREENS
from eternal_realm.bot.services import Services
from eternal_realm.config import Settings
from eternal_realm.context import AppContext
from eternal_realm.db.repos import wallet
from eternal_realm.game.data import academy as data
from eternal_realm.game.services.academy import CHECKS

from .harness import Harness


@pytest.fixture
def services(db, clock, rng):
    return Services.build(AppContext(db, Settings(token="t", owner_id=999), clock=clock, rng=rng))


@pytest.fixture
def h(services):
    return Harness(services)


async def hero(services, db, uid=1, level=10):
    p = await services.players.register(uid, f"u{uid}", f"قهرمان{uid}", "elf", "warrior")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET level = ?, energy = 500 WHERE id = ?", (level, p.id))
        await wallet.apply(tx, p.id, gold=3_000, reason="t", now=services.ctx.now())
    return await services.players.require(uid)


def notes(h) -> list[str]:
    return [m["text"] for m in h.session.sent() if "آفرین! درس" in m.get("text", "")]


# --- the lessons themselves ----------------------------------------------------------------------------------------
def test_every_lesson_leads_to_a_real_screen_command_and_check():
    commands = {c.name for c in REGISTRY.all()}
    for lesson in data.LESSONS:
        assert lesson.teach and lesson.task and lesson.after, lesson.id
        assert lesson.go or lesson.say or lesson.in_group, lesson.id  # the player is always told where to go
        assert lesson.visit or lesson.commands or lesson.check, lesson.id  # and the academy can always notice it
        if lesson.go:
            assert lesson.go[1] in SCREENS, lesson.id
        assert all(s in SCREENS for s in lesson.visit), lesson.id
        assert all(c in commands for c in lesson.commands), lesson.id
        if lesson.check and not lesson.check.startswith(("deed:", "ledger:")):
            assert lesson.check in CHECKS, lesson.id
    assert {lesson.chapter for lesson in data.LESSONS} == {c.number for c in data.CHAPTERS}
    assert len({lesson.id for lesson in data.LESSONS}) == len(data.LESSONS)


async def test_every_check_runs_on_the_real_schema(services, db):
    p = await hero(services, db)
    async with db.read() as tx:
        for lesson in data.LESSONS:
            assert await services.academy._fact(tx, p.id, lesson) is False, lesson.id


# --- learning by doing -------------------------------------------------------------------------------------------------
async def test_the_menu_has_the_academy_instead_of_the_help(h, services, db):
    await hero(services, db)
    await h.panel(1, "home")
    labels = " ".join(h.labels())
    assert "🎓 آکادمی" in labels and "راهنمایی" not in labels
    h.session.reset()
    await h.say(1, "راهنما")
    assert "آکادمی قلمرو" in h.session.last_text()


async def test_a_visit_and_a_word_teach_their_lessons_with_a_note_and_a_reward(h, services, db):
    await hero(services, db)
    await h.panel(1, "academy")
    assert "آکادمی قلمرو" in h.session.last_text() and "۰ از" in h.session.last_text()
    gold = (await services.players.require(1)).gold
    h.session.reset()
    await h.panel(1, "profile")  # the first lesson: look at your hero
    assert any("قهرمان تو" in n for n in notes(h))
    assert (await services.players.require(1)).gold == gold + data.LESSON_BY_ID["hero"].gold
    assert "جایزه‌ی روزانه" in h.session.last_text()  # the note points at the next lesson
    h.session.reset()
    await h.say(1, "جایزه")  # the daily gift, claimed with a word
    assert any("جایزه‌ی روزانه" in n for n in notes(h))
    state = await services.academy.state((await services.players.require(1)).id)
    assert {"hero", "daily"} <= state.done and state.current.id == "energy"


async def test_sending_hunt_teaches_the_hunt_lesson(h, services, db):
    p = await hero(services, db)
    await services.academy.start(p.id)
    for lesson_id in ("hero", "daily", "energy", "missions", "activity"):
        await services.academy.skip(p.id, lesson_id)
    assert (await services.academy.state(p.id)).current.id == "hunt"
    h.session.reset()
    await h.say(1, "شکار")
    assert any("شکار" in n and "هیولا" in n for n in notes(h))
    assert "hunt" in (await services.academy.state(p.id)).done


async def test_the_practice_fight_is_free_and_is_learned_by_winning(h, services, db):
    p = await hero(services, db)
    await services.academy.start(p.id)
    for lesson in data.LESSONS[: [x.id for x in data.LESSONS].index("fight")]:
        await services.academy.skip(p.id, lesson.id)
    energy = (await services.players.require(1)).energy
    await h.panel(1, "acfight")
    assert "گابلین تمرینی" in h.session.last_text()
    assert (await services.players.require(1)).energy == energy  # no energy for practice
    for _ in range(40):
        if await services.solo.active(p.id) is None:
            break
        await h.panel(1, "sact", "attack")
    assert "fight" in (await services.academy.state(p.id)).done
    assert any("نبرد تمرینی" in n for n in notes(h))
    assert any("آکادمی" in b["text"] for b in h.session.last_buttons())


async def test_opening_the_academy_ticks_what_the_hero_already_knows(h, services, db):
    p = await hero(services, db)
    async with db.transaction() as tx:
        await tx.execute("INSERT INTO deed_counts (player_id, deed, n) VALUES (?, 'hunt', 3)", (p.id,))
    await h.panel(1, "academy")
    assert "از قبل بلد بودی" in h.session.last_text()
    assert "hunt" in (await services.academy.state(p.id)).done


async def test_a_put_off_lesson_is_still_learned_later(h, services, db):
    p = await hero(services, db)
    await services.academy.skip(p.id, "group")
    state = await services.academy.state(p.id)
    assert "group" in state.skipped and state.current.id == "hero"
    assert await services.academy.check(p, "group") is None  # not in a group yet
    await services.groups.touch(-500, "گروه")
    async with db.transaction() as tx:
        await tx.execute("INSERT INTO group_members (chat_id, player_id, points, last_active) VALUES (-500, ?, 0, 0)", (p.id,))
    assert (await services.academy.check(p, "group")).lesson.id == "group"


async def test_a_hero_outside_the_academy_gets_no_notes(h, services, db):
    await hero(services, db)
    h.session.reset()
    await h.panel(1, "profile")
    assert notes(h) == []


async def test_every_lesson_chapter_and_the_graduation_pay_once(services, db):
    p = await hero(services, db)
    before = await services.players.require(1)
    async with db.transaction() as tx:
        state = await services.academy._state(tx, p.id)
        done = [await services.academy._complete(tx, p.id, lesson, state) for lesson in data.LESSONS]
        again = await services.academy._complete(tx, p.id, data.LESSONS[0], state)
    assert again is None
    assert [d.chapter.number for d in done if d.chapter] == [c.number for c in data.CHAPTERS]
    assert done[-1].graduated and sum(d.graduated for d in done) == 1
    after = await services.players.require(1)
    assert after.gold == before.gold + sum(x.gold for x in data.LESSONS)
    assert after.crystal == before.crystal + data.GRADUATION_CRYSTAL
    async with db.read() as tx:
        assert await tx.scalar("SELECT text FROM player_titles WHERE player_id = ? AND key = 'academy'", (p.id,)) == data.GRADUATION_TITLE
    view = dict((i.id, q) for i, q in (await services.inventory.view(p.id)).stacks)
    assert view.get("royal_chest") == 1 + sum(1 for c in data.CHAPTERS if c.chest == "royal_chest")
    assert (await services.academy.state(p.id)).graduated


async def test_a_new_hero_is_invited_to_the_academy(h, services):
    await h.say(7, "/start")
    await h.say(7, "نگار")
    await h.click(7, RaceCb(id="elf").pack())
    await h.click(7, ClassCb(id="archer").pack())
    invite = next(m for m in h.session.sent() if "آکادمی" in m.get("text", "") and "تازه‌واردی" in m["text"])
    assert "شروع آکادمی" in str(invite)
    p = await services.players.find(7)
    assert (await services.academy.state(p.id)).started

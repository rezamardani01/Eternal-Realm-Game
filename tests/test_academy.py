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
from eternal_realm.shared.errors import GameError

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


async def learn_before(services, db, p, lesson_id):
    """Learn every lesson before ``lesson_id`` (the way a hero would, in order) so that it is the open one."""
    await services.academy.start(p.id)
    async with db.transaction() as tx:
        state = await services.academy._state(tx, p.id)
        for lesson in data.LESSONS:
            if lesson.id == lesson_id:
                break
            await services.academy._complete(tx, p.id, lesson, state)


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
    await h.panel(1, "aclesson", "hero")  # the lesson is opened: the academy mode
    h.session.reset()
    await h.panel(1, "profile")  # the first lesson: look at your hero
    assert any("قهرمان تو" in n for n in notes(h))
    assert (await services.players.require(1)).gold == gold + data.LESSON_BY_ID["hero"].gold
    assert "جایزه‌ی روزانه" in h.session.last_text()  # the note points at the next lesson
    await h.tap(1, "درس بعدی")  # the button of the note opens the next lesson
    h.session.reset()
    await h.say(1, "جایزه")  # the daily gift, claimed with a word
    assert any("جایزه‌ی روزانه" in n for n in notes(h))
    state = await services.academy.state((await services.players.require(1)).id)
    assert {"hero", "daily"} <= state.done and state.current.id == "energy"


async def test_sending_hunt_teaches_the_hunt_lesson(h, services, db):
    p = await hero(services, db)
    await learn_before(services, db, p, "hunt")
    assert (await services.academy.state(p.id)).current.id == "hunt"
    await h.panel(1, "aclesson", "hunt")
    h.session.reset()
    await h.say(1, "شکار")
    assert any("شکار" in n and "هیولا" in n for n in notes(h))
    assert "hunt" in (await services.academy.state(p.id)).done


async def test_the_practice_fight_is_free_and_is_learned_by_winning(h, services, db):
    p = await hero(services, db)
    await learn_before(services, db, p, "fight")
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


async def test_opening_the_academy_ticks_what_the_hero_already_knows_in_order(h, services, db):
    p = await hero(services, db)
    async with db.transaction() as tx:  # the hero already hunted, but never opened the first lessons
        await tx.execute("INSERT INTO deed_counts (player_id, deed, n) VALUES (?, 'hunt', 3)", (p.id,))
    await h.panel(1, "academy")
    assert "hunt" not in (await services.academy.state(p.id)).done  # locked behind the first lessons
    await learn_before(services, db, p, "activity")
    await h.panel(1, "academy")
    assert "hunt" not in (await services.academy.state(p.id)).done  # «activity» comes first and is not done
    async with db.transaction() as tx:
        await tx.execute("INSERT INTO deed_counts (player_id, deed, n) VALUES (?, 'activity', 1)", (p.id,))
    await h.panel(1, "academy")
    assert {"activity", "hunt"} <= (await services.academy.state(p.id)).done
    assert "از قبل بلد بودی" in h.session.last_text()


async def test_lessons_are_locked_until_the_ones_before_are_learned(h, services, db):
    p = await hero(services, db)
    await h.panel(1, "aclesson", "hunt")  # far ahead
    text = h.session.last_text()
    assert "🔒" in text and "قهرمان تو" in text  # told which lesson comes first
    assert not any("بررسی" in b["text"] for b in h.session.last_buttons())
    assert any("برو به درس" in b["text"] for b in h.session.last_buttons())
    # a word and a check do not teach a locked lesson
    await services.academy.start(p.id)
    h.session.reset()
    await h.say(1, "شکار")
    assert "hunt" not in (await services.academy.state(p.id)).done and notes(h) == []
    async with db.read() as tx:  # the real hunt happened, so the deed is in the database ...
        assert await tx.scalar("SELECT n FROM deed_counts WHERE player_id = ? AND deed = 'hunt'", (p.id,), 0) >= 1
    assert await services.academy.check(p, "hunt") is None  # ... yet the locked lesson is not learned
    # lessons are learned in order, and the next one opens
    await h.panel(1, "aclesson", "hero")
    await h.panel(1, "profile")
    assert (await services.academy.state(p.id)).done == {"hero"}
    await h.panel(1, "aclesson", "daily")
    assert "🔒" not in h.session.last_text() and "جایزه‌ی روزانه" in h.session.last_text()


async def test_only_group_and_city_lessons_can_be_put_off(h, services, db):
    p = await hero(services, db)
    await services.academy.start(p.id)
    with pytest.raises(GameError):
        await services.academy.skip(p.id, "hero")  # an ordinary lesson cannot be skipped
    with pytest.raises(GameError):
        await services.academy.skip(p.id, "group")  # and not before it opens
    await learn_before(services, db, p, "group")
    await services.academy.skip(p.id, "group")
    state = await services.academy.state(p.id)
    assert state.current.id == "duel"  # the ones after it open
    assert not state.unlocked(data.LESSON_BY_ID["city"])  # but the city waits for the group lessons
    await services.academy.skip(p.id, "duel")
    await services.academy.skip(p.id, "boss")
    assert (await services.academy.state(p.id)).current.id == "city"
    # a put-off lesson is still learned later, and pays
    await services.groups.touch(-500, "گروه")
    async with db.transaction() as tx:
        await tx.execute("INSERT INTO group_members (chat_id, player_id, points, last_active) VALUES (-500, ?, 0, 0)", (p.id,))
    assert (await services.academy.check(p, "group")).lesson.id == "group"


async def test_chapter_buttons_are_numbered_and_locked_chapters_show_a_lock(h, services, db):
    await hero(services, db)
    await h.panel(1, "academy")
    labels = h.labels()
    assert any(label.startswith("▶️ ۱.") and "قدم اول" in label for label in labels)
    assert any(label.startswith("🔒 ۲.") and "ماجراجویی" in label for label in labels)
    assert any(label.startswith("🔒 ۸.") for label in labels)
    await h.panel(1, "acchap", "1")
    assert any(label.startswith("▶️ ۱.") for label in h.labels())  # the lessons are numbered too
    assert any(label.startswith("🔒 ۲.") for label in h.labels())
    await h.panel(1, "acchap", "2")
    assert "🔒 این فصل هنوز قفل است" in h.session.last_text()


async def test_lessons_answer_the_questions_a_new_player_has(h, services, db):
    p = await hero(services, db)
    await h.panel(1, "aclesson", "hero")
    text = h.session.last_text()
    assert "سؤال‌هایی که شاید داشته باشی" in text and "قهرمانم چطور قوی‌تر می‌شود؟" in text
    await learn_before(services, db, p, "upgrade")
    await h.panel(1, "aclesson", "upgrade")
    assert "سنگ آهن و پاره‌کریستال را از کجا بیاورم؟" in h.session.last_text() and "معدن" in h.session.last_text()
    assert all(lesson.faq for lesson in data.LESSONS if lesson.id not in {"top", "invite"})


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
    invite = next(m for m in h.session.sent() if "آکادمی" in m.get("text", "") and "قدم بعدی: آکادمی" in m["text"])
    assert "شروع آکادمی" in str(invite)
    p = await services.players.find(7)
    assert (await services.academy.state(p.id)).started


# --- never stuck, never broken midway ---------------------------------------------------------------------------------
async def test_a_refused_rest_still_teaches_lesson_3_of_chapter_1_with_a_note(h, services, db):
    p = await hero(services, db)
    await h.panel(1, "aclesson", "hero")
    await h.panel(1, "profile")
    await h.panel(1, "aclesson", "daily")
    await h.say(1, "جایزه")
    assert (await services.academy.state(p.id)).current.id == "energy"
    await h.panel(1, "aclesson", "energy")  # the lesson is open; the hero has full energy
    h.session.reset()
    await h.say(1, "استراحت")  # the game answers «سرشار از انرژی هستید» ...
    assert any("سرشار از انرژی" in t for t in h.session.texts())
    note = next(n for n in notes(h))  # ... and the academy still says well done
    assert "درس ۳ فصل ۱ تکمیل شد" in note and "انرژی و استراحت" in note and "۳ از ۳۹" in note
    assert "energy" in (await services.academy.state(p.id)).done
    assert "مأموریت‌های روزانه" in note  # and points to the next lesson


async def test_a_refused_rest_button_teaches_it_too_but_other_refused_tries_do_not(h, services, db):
    p = await hero(services, db)
    await learn_before(services, db, p, "energy")
    await h.panel(1, "aclesson", "energy")
    h.session.reset()
    await h.panel(1, "rest")  # the button: refused (full energy), still learned
    assert any("درس ۳ فصل ۱" in n for n in notes(h))
    # a refused try of a lesson that is about doing (the hunt, with no energy) teaches nothing
    await learn_before(services, db, p, "hunt")
    await h.panel(1, "aclesson", "hunt")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET energy = 0 WHERE id = ?", (p.id,))
    h.session.reset()
    await h.say(1, "شکار")
    assert notes(h) == [] and "hunt" not in (await services.academy.state(p.id)).done


async def test_a_level_up_from_a_lesson_reward_never_breaks_the_note(h, services, db):
    p = await hero(services, db, level=1)
    await h.panel(1, "aclesson", "hero")
    async with db.transaction() as tx:  # one xp short of the next level
        await tx.execute("UPDATE players SET xp = ? WHERE id = ?", (services.characters.xp_needed(p) - 1, p.id))
    h.session.reset()
    await h.panel(1, "profile")
    assert any("به سطح" in n and "رسیدی" in n for n in notes(h))
    assert (await services.players.require(1)).level == 2


async def test_winning_a_fight_that_levels_the_hero_up_shows_the_result(h, services, db):
    p = await hero(services, db, level=1)
    await learn_before(services, db, p, "fight")
    await h.panel(1, "acfight")
    fresh = await services.players.require(1)  # the lessons before it already raised the level
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET xp = ? WHERE id = ?", (services.characters.xp_needed(fresh) - 1, p.id))
    for _ in range(40):
        if await services.solo.active(p.id) is None:
            break
        await h.panel(1, "sact", "attack")
    shown = [payload.get("text", "") for name, payload in h.session.calls if name in ("sendMessage", "editMessageText")]
    assert any("به سطح" in t and "رسیدید" in t for t in shown)  # the fight's result screen, level-up line included
    assert (await services.players.require(1)).level >= 2
    assert "fight" in (await services.academy.state(p.id)).done


async def test_a_bug_inside_the_academy_never_breaks_the_game(h, services, db, monkeypatch):
    p = await hero(services, db)
    await services.academy.start(p.id)

    async def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(services.academy, "after", broken)
    h.session.reset()
    await h.say(1, "ماهیگیری")  # the work is done and answered as usual
    assert any("ماهیگیر" in t or "🎣" in t for t in h.session.texts())
    await h.panel(1, "profile")
    assert "قهرمان" in h.session.last_text()


async def test_every_lesson_screen_opens_for_a_brand_new_hero(h, services, db):
    p = await hero(services, db, level=1)
    ctxs = []
    for lesson in data.LESSONS:
        if lesson.go and lesson.go[1] not in {"citybuild", "citytroops"}:  # those need a city (the lessons may be put off)
            await h.panel(1, lesson.go[1], lesson.go[2])
            ctxs.append(lesson.id)
            assert h.session.last_text(), lesson.id
            assert not any("قدیمی است" in str(a) for a in h.session.callback_answers()), lesson.id  # no dead button
    assert len(ctxs) >= 30


async def test_lessons_that_need_something_the_hero_may_lack_can_be_put_off(services, db):
    p = await hero(services, db)
    skippable = {x.id for x in data.LESSONS if x.skippable}
    assert {"shop", "upgrade", "sell", "group", "duel", "boss", "city", "build", "troops"} == skippable
    assert all(x.go for x in data.LESSONS if x.id in {"activity", "hunt", "shop", "upgrade", "sell"})  # a button, not only a word
    # nothing else can trap a hero: the only lessons without a way to be learned are the group ones, which can wait
    assert all(x.skippable for x in data.LESSONS if x.in_group)


async def test_a_lost_story_stage_still_teaches_the_story_lesson(services, db):
    p = await hero(services, db)
    await learn_before(services, db, p, "story")
    async with db.transaction() as tx:  # the day's use of the story was spent on a lost stage
        await tx.execute(
            "INSERT INTO solo_fights (player_id, kind, status, state, info, created_at, updated_at) VALUES (?, 'story', 'lost', '{}', '{}', 0, 0)",
            (p.id,),
        )
    assert (await services.academy.check(p, "story")).lesson.id == "story"


async def test_a_hero_who_already_claimed_the_daily_gift_has_learned_it(services, db):
    p = await hero(services, db)
    await learn_before(services, db, p, "daily")
    async with db.transaction() as tx:
        await tx.execute("UPDATE players SET daily_at = ? WHERE id = ?", (services.ctx.now(), p.id))
    assert (await services.academy.check(p, "daily")).lesson.id == "daily"


async def test_the_first_chapter_can_be_walked_from_start_to_finish_with_a_note_at_every_step(h, services, db):
    p = await hero(services, db)
    await h.panel(1, "academy")
    steps = [
        ("hero", lambda: h.panel(1, "profile")),
        ("daily", lambda: h.say(1, "جایزه")),
        ("energy", lambda: h.say(1, "استراحت")),  # refused by the game (full energy), learned anyway
        ("missions", lambda: h.panel(1, "missions")),
    ]
    for lesson_id, act in steps:
        before = len(notes(h))
        await h.panel(1, "aclesson", lesson_id)  # each lesson is opened first, like a player would
        await act()
        assert lesson_id in (await services.academy.state(p.id)).done, lesson_id
        assert len(notes(h)) == before + 1, lesson_id  # exactly one well done per lesson, never two, never none
    state = await services.academy.state(p.id)
    assert state.current.id == "activity" and state.chapter_done(1) == 4
    assert any("فصل «قدم اول» تمام شد" in n for n in notes(h))  # the chapter is finished, its chest paid
    view = dict((i.id, q) for i, q in (await services.inventory.view(p.id)).stacks)
    assert view.get("wooden_chest") == 1
    # a second try of anything already learned says nothing more and pays nothing more
    gold = (await services.players.require(1)).gold
    h.session.reset()
    await h.say(1, "استراحت")
    await h.panel(1, "missions")
    assert notes(h) == [] and (await services.players.require(1)).gold == gold


# --- the academy speaks only while the hero is in it --------------------------------------------------------------------
async def test_the_academy_stays_silent_when_the_hero_plays_normally(h, services, db):
    p = await hero(services, db)
    await services.academy.start(p.id)  # the hero is registered in the academy (a new hero is) but has opened no lesson
    h.session.reset()
    for word in ("جایزه", "استراحت", "ماهیگیری", "شکار"):
        await h.say(1, word)
    await h.panel(1, "profile")
    await h.panel(1, "missions")
    assert notes(h) == []
    assert (await services.academy.state(p.id)).done == set()  # and nothing was ticked behind their back
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM transactions WHERE reason = 'academy'", default=0) == 0


async def test_a_lesson_counts_only_while_it_is_the_one_being_learned(h, services, db, clock):
    p = await hero(services, db)
    await h.panel(1, "aclesson", "hero")  # the mode starts with this lesson
    clock.advance(31 * 60)  # the hero wanders off for half an hour and plays as usual
    h.session.reset()
    await h.panel(1, "profile")
    assert notes(h) == [] and (await services.academy.state(p.id)).active is None
    await h.panel(1, "aclesson", "hero")  # back in the academy
    assert (await services.academy.state(p.id)).active == "hero"
    clock.advance(29 * 60)
    await h.panel(1, "profile")
    assert any("قهرمان تو" in n for n in notes(h))


async def test_only_the_open_lesson_is_noticed_and_the_mode_ends_when_it_is_learned(h, services, db):
    p = await hero(services, db)
    await h.panel(1, "aclesson", "hero")
    h.session.reset()
    await h.say(1, "جایزه")  # the next lesson's deed: not the open lesson, so no word about it
    assert notes(h) == [] and (await services.academy.state(p.id)).done == set()
    await h.panel(1, "profile")
    assert [n for n in notes(h)] and (await services.academy.state(p.id)).done == {"hero"}
    assert (await services.academy.state(p.id)).active is None  # learned: the mode ends until the next lesson is opened
    h.session.reset()
    await h.panel(1, "missions")
    await h.say(1, "استراحت")
    assert notes(h) == []


async def test_opening_a_lesson_whose_deed_is_already_done_ticks_it_on_the_spot(h, services, db):
    p = await hero(services, db)
    await learn_before(services, db, p, "hunt")
    async with db.transaction() as tx:
        await tx.execute("INSERT INTO deed_counts (player_id, deed, n) VALUES (?, 'hunt', 2)", (p.id,))
    await h.panel(1, "aclesson", "hunt")
    assert "hunt" in (await services.academy.state(p.id)).done and "تکمیل شد" in h.session.last_text()


# --- the group lesson: «پروفایل» said in a group ---------------------------------------------------------------------------
async def test_the_profile_word_in_a_group_teaches_the_group_lesson_and_in_private_it_does_not(h, services, db):
    p = await hero(services, db)
    await learn_before(services, db, p, "group")
    await h.panel(1, "aclesson", "group")
    assert not any("بررسی" in b["text"] for b in h.session.last_buttons())  # no check button: the word is noticed at once
    h.session.reset()
    await h.say(1, "پروفایل")  # in the private chat: that is not what the lesson asks
    assert notes(h) == [] and "group" not in (await services.academy.state(p.id)).done
    await h.say(1, "پروفایل", group=True)  # in a group: well done, sent to the hero's private chat
    note = next(m for m in h.session.sent() if "آفرین! درس" in m.get("text", ""))
    assert "درس ۱ فصل ۷ تکمیل شد" in note["text"] and note["chat_id"] == 1
    assert "group" in (await services.academy.state(p.id)).done


async def test_the_group_lesson_is_not_taught_by_a_group_word_outside_the_academy(h, services, db):
    p = await hero(services, db)
    await learn_before(services, db, p, "group")  # the lesson is next, but the hero never opened it
    h.session.reset()
    await h.say(1, "پروفایل", group=True)
    assert notes(h) == [] and "group" not in (await services.academy.state(p.id)).done


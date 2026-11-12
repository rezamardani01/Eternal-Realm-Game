"""«🎓 آکادمی»: the game taught chapter by chapter in plain words, and the note that tells a hero a lesson was learned."""

from __future__ import annotations

import contextlib
import logging

from baleropy import Button

from ..game.data import academy as data
from ..game.data.items import get_item
from ..game.models import Player
from ..game.services.academy import AcademyState, Completion
from ..shared.errors import GameError
from ..shared.text import bar, bold, fa
from .callbacks import PanelCb
from .panel import Ctx, Screen, screen
from .services import Services

log = logging.getLogger(__name__)

#: the academy's own screens: opening them never counts as «doing» a lesson
SCREENS = frozenset({"academy", "acchap", "aclesson", "accheck", "acskip", "acfight", "help", "helpsec"})


def _mark(state: AcademyState, lesson: data.Lesson) -> str:
    if lesson.id in state.done:
        return "✅"
    if state.current is not None and lesson.id == state.current.id:
        return "▶️"
    if lesson.id in state.skipped:
        return "⏭️"
    return "▫️"


def _reward(lesson: data.Lesson) -> str:
    return f"🪙 {fa(lesson.gold)} سکه · ⭐ {fa(lesson.xp)} تجربه"


def done_lines(done: Completion) -> list[str]:
    """What a learned lesson says: the praise, what just happened, the reward, a finished chapter, the graduation."""
    lines = [f"🎓 {bold('آفرین! درس «' + done.lesson.title + '» را یاد گرفتی')} ✅", "", done.lesson.after, "",
             f"🎁 جایزه: {_reward(done.lesson)}"]
    if done.level_up:
        lines.append(f"🎉 به سطح {fa(done.level_up.new)} رسیدی!")
    if done.chapter:
        lines += ["", f"🏅 {bold('فصل «' + done.chapter.name + '» تمام شد!')}", f"جایزه‌ی فصل: {get_item(done.chapter.chest).label} 📦"]
    if done.graduated:
        lines += [
            "", f"🎓🎉 {bold('تبریک! آکادمی را تمام کردی!')}",
            f"حالا همه‌چیز بازی را بلدی. جایزه‌ی فارغ‌التحصیلی: 💎 {fa(data.GRADUATION_CRYSTAL)} کریستال، "
            f"{get_item(data.GRADUATION_CHEST).label} و عنوان «{data.GRADUATION_TITLE}» روی پروفایلت.",
        ]
    return lines


async def notify(bot, services: Services, player: Player, chat_id: int, completions: list[Completion]) -> None:  # noqa: ANN001 - Bot
    """Tell the hero, in a message of its own, which lessons they just learned and where to go next."""
    if not completions:
        return
    state = await services.academy.state(player.id)
    lines: list[str] = []
    for done in completions:
        lines += [*done_lines(done), ""]
    nxt = state.current
    owner = player.platform_user_id
    rows = []
    if nxt is not None and not state.graduated:
        lines.append(f"➡️ درس بعدی: {nxt.emoji} {bold(nxt.title)}")
        rows.append([Button.inline(f"➡️ درس بعدی: {nxt.title}", PanelCb(s="aclesson", a=nxt.id, b=None, o=owner), style="success")])
    rows.append([Button.inline("🎓 آکادمی", PanelCb(s="academy", a=None, b=None, o=owner))])
    with contextlib.suppress(Exception):  # a hero who never opened the private chat cannot be told; that is all
        await bot.send_message(chat_id, "\n".join(lines).strip(), buttons=rows)


async def after(bot, services: Services, player: Player, chat_id: int, *, screen: str = "", command: str = "") -> None:  # noqa: ANN001
    """The academy's look after anything the hero did; quiet unless a lesson was learned."""
    if screen in SCREENS:
        return
    try:
        completions = await services.academy.after(player, screen=screen, command=command)
    except Exception:  # the academy must never break the game it teaches
        log.exception("academy check failed")
        return
    await notify(bot, services, player, chat_id, completions)


# --- the screens ------------------------------------------------------------------------------------------------------
def _private(c: Ctx) -> None:
    if c.is_group:
        raise GameError("آکادمی در پیام خصوصی ربات باز می‌شود؛ آنجا بیا 🙂")


@screen("academy")
async def academy(c: Ctx) -> Screen:
    _private(c)
    learned = await c.services.academy.sync(c.player)
    state = await c.services.academy.state(c.player.id)
    total, done = len(data.LESSONS), len(state.done)
    lines = [
        f"🎓 {bold('آکادمی قلمرو')}",
        "",
        "این‌جا قدم به قدم همه‌چیز بازی را یاد می‌گیری؛ هر درس را خودت انجام می‌دهی و برایش جایزه می‌گیری! 🎁",
        "",
        f"📚 پیشرفت تو: {fa(done)} از {fa(total)} درس",
        bar(done, total, 10),
        "",
    ]
    for chapter in data.CHAPTERS:
        have, size = state.chapter_done(chapter.number), len(data.lessons_of(chapter.number))
        mark = "✅" if have == size else "▶️" if state.current and state.current.chapter == chapter.number else "📘"
        lines.append(f"{mark} فصل {fa(chapter.number)}: {chapter.emoji} {chapter.name} ({fa(have)}/{fa(size)})")
    if learned:
        lines += ["", f"✨ {fa(len(learned))} درس را از قبل بلد بودی و تیک خوردند؛ جایزه‌شان هم به کیفت آمد!"]
    if state.graduated:
        lines += ["", f"🎓 تو {bold('فارغ‌التحصیل')} آکادمی هستی! هر وقت خواستی درس‌ها را دوباره بخوان."]
    rows = []
    nxt = state.current or state.next_open
    if nxt is not None:
        rows.append([c.btn(f"▶️ ادامه: {nxt.emoji} {nxt.title}", "aclesson", nxt.id, style="success")])
    chapter_buttons = [c.btn(f"{ch.emoji} {ch.name}", "acchap", ch.number) for ch in data.CHAPTERS]
    rows += [chapter_buttons[i:i + 2] for i in range(0, len(chapter_buttons), 2)]
    rows.append([c.btn("📖 فهرست همه‌ی دستورها", "help")])
    rows.append(c.back("home"))
    return Screen("\n".join(lines), rows)


@screen("acchap")
async def chapter_view(c: Ctx) -> Screen:
    _private(c)
    chapter = data.CHAPTER_BY_NUMBER.get(int(c.a or 1))
    if chapter is None:
        raise KeyError(c.a)
    state = await c.services.academy.state(c.player.id)
    lessons = data.lessons_of(chapter.number)
    lines = [
        f"{chapter.emoji} {bold('فصل ' + fa(chapter.number) + ': ' + chapter.name)}",
        chapter.about,
        "",
        f"📚 {fa(state.chapter_done(chapter.number))} از {fa(len(lessons))} درس · جایزه‌ی فصل: {get_item(chapter.chest).label}",
        "",
    ]
    lines += [f"{_mark(state, x)} {x.emoji} {x.title}" for x in lessons]
    rows = [[c.btn(f"{_mark(state, x)} {x.title}", "aclesson", x.id)] for x in lessons]
    rows.append(c.back("academy", "🎓 آکادمی"))
    return Screen("\n".join(lines), rows)


def lesson_screen(c: Ctx, state: AcademyState, lesson: data.Lesson) -> Screen:
    chapter = data.CHAPTER_BY_NUMBER[lesson.chapter]
    lessons = data.lessons_of(lesson.chapter)
    number = lessons.index(lesson) + 1
    lines = [
        f"🎓 فصل {fa(chapter.number)} · {chapter.name} · درس {fa(number)} از {fa(len(lessons))}",
        "",
        f"{lesson.emoji} {bold(lesson.title)}",
        "",
        lesson.teach,
        "",
    ]
    rows = []
    if lesson.id in state.done:
        lines += [f"✅ {bold('این درس را یاد گرفتی!')}", lesson.after]
    else:
        lines += [f"👇 {bold('کار تو:')}", lesson.task]
        if lesson.say:
            where = " (در گروه)" if lesson.in_group else ""
            lines += ["", f"✍️ بنویس{where}: «{bold(lesson.say)}»"]
        lines += ["", f"🎁 جایزه‌ی این درس: {_reward(lesson)}"]
        if lesson.go:
            label, target, arg = lesson.go
            rows.append([c.btn(label, target, arg, style="primary")])
        if lesson.say and not lesson.in_group:
            rows.append([Button.copy_text(f"📋 کپی کلمه‌ی «{lesson.say}»", lesson.say)])
        if lesson.check:
            rows.append([c.btn("🔍 انجام دادم، بررسی کن", "accheck", lesson.id, style="success")])
        rows.append([c.btn("⏭️ بعداً یاد می‌گیرم", "acskip", lesson.id)])
    nxt = next((x for x in data.LESSONS[data.LESSONS.index(lesson) + 1:] if x.id not in state.done), None)
    if lesson.id in state.done and nxt is not None:
        rows.append([c.btn(f"➡️ درس بعدی: {nxt.title}", "aclesson", nxt.id, style="success")])
    rows.append([c.btn(f"{chapter.emoji} فصل {chapter.name}", "acchap", chapter.number), c.btn("🎓 آکادمی", "academy")])
    return Screen("\n".join(lines), rows)


@screen("aclesson")
async def lesson_view(c: Ctx) -> Screen:
    _private(c)
    lesson = data.LESSON_BY_ID[c.a]
    await c.services.academy.start(c.player.id)
    return lesson_screen(c, await c.services.academy.state(c.player.id), lesson)


@screen("accheck")
async def lesson_check(c: Ctx) -> Screen:
    _private(c)
    lesson = data.LESSON_BY_ID[c.a]
    done = await c.services.academy.check(c.player, lesson.id)
    state = await c.services.academy.state(c.player.id)
    if done is None and lesson.id not in state.done:
        shown = lesson_screen(c, state, lesson)
        shown.toast, shown.alert = "هنوز انجامش نداده‌ای! کار این درس را انجام بده و دوباره بزن 🙂", True
        return shown
    shown = lesson_screen(c, state, lesson)
    if done is not None:
        shown.text = "\n".join(done_lines(done))
        shown.toast = "آفرین! 🎉"
    return shown


@screen("acskip")
async def lesson_skip(c: Ctx) -> Screen:
    _private(c)
    lesson = data.LESSON_BY_ID[c.a]
    await c.services.academy.skip(c.player.id, lesson.id)
    state = await c.services.academy.state(c.player.id)
    nxt = state.current
    if nxt is None:
        return await academy(c)
    shown = lesson_screen(c, state, nxt)
    shown.toast = f"«{lesson.title}» ماند برای بعد؛ هر وقت انجامش بدهی، باز هم جایزه‌اش را می‌گیری."
    return shown


@screen("acfight")
async def practice_fight(c: Ctx) -> Screen:
    _private(c)
    from .solo_panel import _start

    fight = await c.services.solo.start_academy(c.player)
    return _start(c, fight)

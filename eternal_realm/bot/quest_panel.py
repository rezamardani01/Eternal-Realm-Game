"""Story quest screens: pick a tale, read each scene, tap a choice."""

from __future__ import annotations

from ..game.data.items import get_item
from ..game.data.story_gen import CHAPTER_LEVELS, CHAPTERS
from ..game.services.quests import QuestView
from ..shared.text import bold, fa
from .panel import Ctx, Screen, _int, screen

STATUS = {"new": "🆕", "running": "📖", "done": "✅", "locked": "🔒"}


@screen("quests")
async def quests(c: Ctx) -> Screen:
    """Ten chapters; each opens at a level and holds ten stories."""
    by_chapter: dict[int, list[str]] = {}
    for quest, status in await c.services.quests.status(c.player):
        by_chapter.setdefault(quest.chapter, []).append(status)
    rows = []
    lines = [
        f"📜 {bold('داستان‌ها')}",
        "",
        "ده فصل داستان در انتظار شماست و هر فصل ده داستان دارد. هر فصل با بالا رفتن سطح باز می‌شود.",
        "هر داستان یک بار پاداش می‌دهد، پس با دقت انتخاب کنید!",
        "",
    ]
    for number in range(1, len(CHAPTERS) + 1):
        emoji, name = CHAPTERS[number - 1][:2]
        statuses = by_chapter.get(number, [])
        done = statuses.count("done")
        need = CHAPTER_LEVELS[number - 1]
        if c.player.level < need:
            label = f"🔒 فصل {fa(number)} · {name} · سطح {fa(need)}"
        else:
            label = f"{emoji} فصل {fa(number)} · {name} · {fa(done)}/{fa(len(statuses))}" + (" ✔" if done == len(statuses) else "")
        rows.append([c.btn(label, "qchapter", number)])
    special = by_chapter.get(0, [])
    if special:
        rows.append([c.btn(f"🌟 داستان‌های ویژه · {fa(special.count('done'))}/{fa(len(special))}", "qchapter", 0)])
    rows.append(c.back("home"))
    return Screen("\n".join(lines), rows)


@screen("qchapter")
async def quest_chapter(c: Ctx) -> Screen:
    number = _int(c.a or "0")
    stories = [(q, st) for q, st in await c.services.quests.status(c.player) if q.chapter == number]
    if not stories:
        return Screen(None, toast="این فصل پیدا نشد.", alert=True)
    if number:
        emoji, name = CHAPTERS[number - 1][:2]
        need = CHAPTER_LEVELS[number - 1]
        title = f"{emoji} {bold(f'فصل {fa(number)}: {name}')}"
    else:
        need, title = 1, f"🌟 {bold('داستان‌های ویژه')}"
    if c.player.level < need:
        text = (
            f"🔒 {bold(f'فصل {fa(number)} هنوز بسته است')}\n\n"
            f"این فصل از سطح {fa(need)} باز می‌شود. شما سطح {fa(c.player.level)} هستید؛ "
            f"{fa(need - c.player.level)} سطح دیگر مانده. با ماجراجویی و نبرد سطح بگیرید!"
        )
        return Screen(text, [c.back("quests", "🔙 فصل‌ها")])
    done = sum(1 for _, st in stories if st == "done")
    rows = [[c.btn(f"{STATUS[st]} {q.title}", "quest", q.id)] for q, st in stories]
    rows.append(c.back("quests", "🔙 فصل‌ها"))
    text = f"{title}\n\n✅ {fa(done)} از {fa(len(stories))} داستان تمام شده.\n\nیک داستان را انتخاب کنید 👇"
    return Screen(text, rows)


def _scene(view: QuestView) -> str:
    quest = view.quest
    lines = [f"{quest.emoji} {bold(quest.title)}", "", view.step.text]
    if view.step.ending:
        lines += ["", f"🎬 {bold(view.step.ending)}"]
    if view.reward is not None:
        r = view.reward
        got = []
        if r.gold:
            got.append(f"{fa(r.gold)} سکه")
        if r.crystal:
            got.append(f"{fa(r.crystal)} کریستال")
        if r.xp:
            got.append(f"{fa(r.xp)} تجربه")
        got += [f"{get_item(i).label} ×{fa(q)}" for i, q in r.items]
        lines += ["", f"🎁 {bold('پاداش شما')}", *got]
        if view.level_up:
            lines += ["", f"🎉 رسیدید به سطح {fa(view.level_up)}"]
    return "\n".join(lines)


async def _show(c: Ctx, view: QuestView) -> Screen:
    rows = [[c.btn(choice.label, "qgo", view.quest.id, i)] for i, choice in view.options]
    rows.append(c.back("qchapter", "🔙 داستان‌های این فصل", view.quest.chapter))
    return Screen(_scene(view), rows)


@screen("quest")
async def quest(c: Ctx) -> Screen:
    view = await c.services.quests.view(c.player, c.a)
    if view.done:
        shown = await _show(c, view)
        shown.text = (shown.text or "") + "\n\n✅ این داستان را به پایان رسانده‌اید."
        return shown
    return await _show(c, view)


@screen("qgo")
async def quest_go(c: Ctx) -> Screen:
    view = await c.services.quests.choose(c.player, c.a, _int(c.b))
    shown = await _show(c, view)
    if view.reward is not None:
        shown.toast = "🎁 پاداش داستان به کیفتان رسید!"
    return shown

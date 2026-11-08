"""Story quest screens: pick a tale, read each scene, tap a choice."""

from __future__ import annotations

from ..game.data.items import get_item
from ..game.services.quests import QuestView
from ..shared.text import bold, fa
from .panel import Ctx, Screen, _int, screen

STATUS = {"new": "🆕", "running": "📖", "done": "✅", "locked": "🔒"}


@screen("quests")
async def quests(c: Ctx) -> Screen:
    rows = []
    for quest, status in await c.services.quests.status(c.player):
        suffix = f" (سطح {fa(quest.level_req)})" if status == "locked" else ""
        rows.append([c.btn(f"{STATUS[status]} {quest.title}{suffix}", "quest", quest.id)])
    rows.append(c.back("home"))
    text = (
        f"📜 {bold('داستان‌ها')}\n\n"
        "هر داستان چند صحنه دارد و انتخاب‌های شما سرنوشتش را می‌سازد. هر داستان فقط یک بار پاداش می‌دهد، "
        "پس با دقت انتخاب کنید!\n\n"
        "🆕 تازه · 📖 نیمه‌کاره · ✅ تمام‌شده · 🔒 قفل"
    )
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
    rows.append(c.back("quests", "🔙 داستان‌ها"))
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

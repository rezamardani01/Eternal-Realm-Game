"""Weekly contest screens."""

from __future__ import annotations

from ..game.services.contests import CONTESTS, PRIZES
from ..shared.text import bold, fa
from .panel import Ctx, Screen, screen

MEDALS = ("🥇", "🥈", "🥉")


@screen("contests")
async def contests(c: Ctx) -> Screen:
    due = await c.services.contests.prizes(c.player)
    lines = [
        f"🏁 {bold('مسابقه‌های هفته')}",
        "",
        "هر هفته (از شنبه) چند مسابقه برگزار می‌شود. سه نفر اول هر مسابقه هفته‌ی بعد جایزه می‌گیرند:",
        "  ".join(f"{m} {fa(g)}🪙" for m, g in zip(MEDALS, PRIZES)),
        "نفر اول عنوان هفته را هم می‌گیرد.",
        "",
        "یک مسابقه را انتخاب کنید 👇",
    ]
    rows = [[c.btn(f"{emoji} {title}", "contest", key)] for key, (emoji, title, _) in CONTESTS.items()]
    if due:
        total = sum(g for _, _, g in due)
        rows.insert(0, [c.btn(f"🎁 دریافت جایزه‌ها ({fa(total)}🪙)", "contestclaim", style="success")])
        lines.insert(2, f"🎉 هفته‌ی پیش در {fa(len(due))} مسابقه جایزه آوردید!")
    rows.append(c.back("top"))
    return Screen("\n".join(lines), rows)


@screen("contest")
async def contest(c: Ctx) -> Screen:
    st = await c.services.contests.standing(c.player, c.a)
    emoji, title, _ = CONTESTS[c.a]
    lines = [f"{emoji} {bold(title)}", "", "رتبه‌بندی این هفته:", ""]
    if not st.rows:
        lines.append("هنوز کسی امتیازی نگرفته. اولین باشید!")
    for i, r in enumerate(st.rows):
        medal = MEDALS[i] if i < 3 else f"{fa(i + 1)}."
        name = f"[{r.name}](uid:{r.uid})" if c.is_group else r.name
        lines.append(f"{medal} {name} — {fa(r.count)}")
    lines.append("")
    if st.my_place:
        lines.append(f"📍 جایگاه شما: {bold(fa(st.my_place))} با {fa(st.my_count)}")
    else:
        lines.append("شما هنوز در این مسابقه امتیازی ندارید.")
    return Screen("\n".join(lines), [c.back("contests")])


@screen("contestclaim")
async def contest_claim(c: Ctx) -> Screen:
    gold = await c.services.contests.claim(c.player)
    shown = await contests(c)
    shown.toast, shown.alert = f"🎁 {fa(gold)} سکه گرفتید!", True
    return shown

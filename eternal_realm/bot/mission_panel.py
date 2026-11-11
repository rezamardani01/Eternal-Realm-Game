"""Today's personal missions."""

from __future__ import annotations

from ..shared.text import bar, bold, fa
from .panel import Ctx, Screen, _int, screen


@screen("missions")
async def missions(c: Ctx) -> Screen:
    todays = await c.services.missions.today(c.player)
    lines = [
        f"📅 {bold('مأموریت‌ها')}",
        "",
        "مخصوص خود شما هستند و هر نیمه‌شب عوض می‌شوند.",
        "",
    ]
    rows = []
    for m in todays:
        state = "✅ گرفته شد" if m.claimed else ("🎁 آماده‌ی دریافت" if m.done else "در جریان")
        lines += [
            f"{m.emoji} {m.title}",
            f"{bar(m.progress, m.target, 8)}  {fa(m.progress)}/{fa(m.target)} · {state}",
            f"پاداش: {fa(m.gold)} سکه + ۲۰ امتیاز مسیر قهرمانی",
            "",
        ]
        if m.done and not m.claimed:
            rows.append([c.btn(f"🎁 دریافت پاداش مأموریت {'ویژه' if m.kind_id == 'welcome' else fa(m.slot + 1)}", "msclaim", m.slot, style="success")])
    if not todays:
        lines.append("برای امروز مأموریتی پیدا نشد.")
    from .habit_panel import week_lines

    week, week_rows = await week_lines(c)
    lines += week
    rows += week_rows
    rows.append(c.back("profile"))
    return Screen("\n".join(lines).strip(), rows)


@screen("msclaim")
async def mission_claim(c: Ctx) -> Screen:
    done = await c.services.missions.claim(c.player, _int(c.a))
    shown = await missions(c)
    shown.toast, shown.alert = f"🎁 {fa(done.gold)} سکه گرفتید!" + (
        f" و چون همه‌ی مأموریت‌های امروز تمام شد، {fa(done.bonus_crystal)} کریستال هدیه!" if done.bonus_crystal else ""
    ), True
    return shown

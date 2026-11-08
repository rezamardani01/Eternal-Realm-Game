"""Achievements: what each goal asks for, how far you are, and the reward to collect."""

from __future__ import annotations

from ..game.data.achievements import reward_text
from ..game.services.achievements import FamilyView
from ..shared.text import bar, bold, fa
from . import keyboards
from .panel import Ctx, Screen, screen


def _label(v: FamilyView) -> str:
    mark = "✅" if v.finished else ("🎁" if v.claimable else v.family.emoji)
    return f"{mark} {v.family.name}"


@screen("ach")
async def achievements(c: Ctx) -> Screen:
    views = await c.services.achievements.overview(c.player)
    total = sum(len(v.family.steps) for v in views)
    done = sum(v.paid for v in views)
    ready = sum(1 for v in views if v.claimable)
    lines = [
        f"🏅 {bold('دستاوردها')}",
        "",
        f"مرحله‌های گرفته‌شده: {fa(done)} از {fa(total)}",
    ]
    if ready:
        lines.append(f"🎁 {fa(ready)} پاداش آماده‌ی دریافت است")
    lines += ["", "روی هر دستاورد بزنید تا بدانید چه کنید و چه پاداشی می‌گیرید 👇", ""]
    for v in views:
        step = v.step
        if step is None:
            lines += [f"✅ {v.family.name} — کامل", ""]
            continue
        shown = min(v.value, step.target)
        lines += [
            f"{v.family.emoji} {v.family.name} — مرحله‌ی {fa(v.paid + 1)} از {fa(len(v.family.steps))}",
            f"{bar(shown, step.target, 8)}  {fa(shown)}/{fa(step.target)}",
            "",
        ]
    buttons = [
        c.btn(_label(v), "achf", v.family.id, style="success" if v.claimable else None) for v in views
    ]
    rows = keyboards.grid(buttons, 2)
    rows.append(c.back("profile"))
    return Screen("\n".join(lines).strip(), rows)


@screen("achf")
async def achievement(c: Ctx) -> Screen:
    v = await c.services.achievements.view(c.player, c.a)
    f = v.family
    lines = [f"{f.emoji} {bold(f.name)}", ""]
    for i, step in enumerate(f.steps):
        number = i + 1
        task = f.how.format(n=fa(step.target))
        if i < v.paid:
            lines += [f"✅ مرحله‌ی {fa(number)}: {task}", f"پاداش گرفته شد: {reward_text(step)}", ""]
            continue
        current = i == v.paid
        mark = "🎁" if current and v.claimable else ("🔸" if current else "▫️")
        lines += [f"{mark} مرحله‌ی {fa(number)}: {task}", f"پاداش: {reward_text(step)}"]
        if current:
            shown = min(v.value, step.target)
            lines.append(f"{bar(shown, step.target, 8)}  {fa(shown)}/{fa(step.target)}")
        lines.append("")
    if v.finished:
        lines.append("همه‌ی مرحله‌های این دستاورد را گرفته‌اید. آفرین فرمانده!")
    elif f.metric.startswith("deed:"):
        lines.append("شمارش از زمان آمدن دستاوردها شروع شده و هر بار انجام کار یکی به آن اضافه می‌شود.")
    rows = []
    if v.claimable:
        rows.append([c.btn(f"🎁 دریافت پاداش مرحله‌ی {fa(v.paid + 1)}", "achc", f.id, style="success")])
    rows.append(c.back("ach"))
    return Screen("\n".join(lines).strip(), rows)


@screen("achc")
async def achievement_claim(c: Ctx) -> Screen:
    family, number, step = await c.services.achievements.claim(c.player, c.a)
    shown = await achievement(c)
    shown.toast, shown.alert = f"🎁 {family.name}، مرحله‌ی {fa(number)}: {reward_text(step)}", True
    return shown

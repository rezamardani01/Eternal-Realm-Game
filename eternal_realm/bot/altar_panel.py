"""The altar: pay a little for a (probably good) blessing, or wash a curse away."""

from __future__ import annotations

from ..game.services.effects import ALTAR_PRICE, BLESSING_CHANCE
from ..shared.text import bold, duration, fa
from .panel import Ctx, Screen, screen


@screen("altar")
async def altar(c: Ctx) -> Screen:
    active = await c.services.effects.active(c.player.id)
    lines = [
        f"🕯️ {bold('محراب')}",
        "",
        "محرابی قدیمی که گاهی نیرویی به مسافران می‌بخشد... و گاهی چیزی از آن‌ها می‌گیرد.",
        "",
        f"💰 هزینه‌ی دعا: {fa(ALTAR_PRICE)} سکه",
        f"✨ شانس برکت: {fa(round(BLESSING_CHANCE * 100))}٪",
        f"🌑 شانس نفرین: {fa(round((1 - BLESSING_CHANCE) * 100))}٪",
        "هر اثر یک ساعت می‌ماند و نفرین‌ها هرگز فقط ضرر نیستند؛ همیشه چیزی هم به شما می‌دهند.",
        "",
    ]
    if active:
        lines.append(bold("اثرهای فعلی شما"))
        for effect, left in active:
            lines.append(f"{effect.emoji} {effect.name} · {duration(left)} مانده")
            lines += [f"   {x}" for x in effect.lines()]
        lines.append("")
    rows = [[c.btn(f"🙏 دعا ({fa(ALTAR_PRICE)}🪙)", "altarq", style="primary")]]
    if any(not e.blessing for e, _ in active):
        rows.append([c.btn(f"🧼 پاک کردن نفرین ({fa(ALTAR_PRICE // 2)}🪙)", "altarcq")])
    rows.append(c.back("profile"))
    return Screen("\n".join(lines).strip(), rows)


@screen("altarq")
async def altar_ask(c: Ctx) -> Screen:
    p = await c.refresh()
    if p.gold < ALTAR_PRICE:
        text = f"💸 {bold('موجودی کافی نیست')}\n\nهزینه: {fa(ALTAR_PRICE)} 🪙\nموجودی شما: {fa(p.gold)} 🪙\nکمبود: {bold(fa(ALTAR_PRICE - p.gold))} 🪙"
        return Screen(text, [c.back("altar")])
    text = (
        f"🙏 {bold('تأیید دعا')}\n\nهزینه: {bold(fa(ALTAR_PRICE))} سکه\n"
        f"کیسه‌ی شما: {fa(p.gold)} ← {fa(p.gold - ALTAR_PRICE)} سکه\n\n"
        f"{fa(round(BLESSING_CHANCE * 100))}٪ برکت، {fa(round((1 - BLESSING_CHANCE) * 100))}٪ نفرین. دعا کنیم؟"
    )
    return Screen(text, [[c.btn("🙏 بله، دعا کن", "altarpray", style="success"), c.btn("↩️ نه", "altar")]])


@screen("altarpray")
async def altar_pray(c: Ctx) -> Screen:
    await c.show(f"🕯️ {bold('دعا')}\n\nشعله‌ی محراب می‌لرزد...")
    effect = await c.services.effects.pray(c.player)
    kind = "برکت" if effect.blessing else "نفرین"
    lines = [f"{effect.emoji} {bold(kind + ' ' + effect.name)}", "", effect.story, "", *effect.lines(), "", f"⏳ {duration(effect.minutes * 60)}"]
    return Screen("\n".join(lines), [[c.btn("🕯️ محراب", "altar"), c.btn("🔙 منو", "home")]])


@screen("altarcq")
async def altar_cleanse_ask(c: Ctx) -> Screen:
    cost = ALTAR_PRICE // 2
    text = f"🧼 {bold('پاک کردن نفرین')}\n\nهزینه: {bold(fa(cost))} سکه. همه‌ی نفرین‌های فعلی برداشته می‌شود. مطمئنید؟"
    return Screen(text, [[c.btn("🧼 بله، پاک کن", "altarclean", style="success"), c.btn("↩️ نه", "altar")]])


@screen("altarclean")
async def altar_cleanse(c: Ctx) -> Screen:
    n = await c.services.effects.cleanse(c.player)
    shown = await altar(c)
    shown.toast = f"🧼 {fa(n)} نفرین پاک شد"
    return shown

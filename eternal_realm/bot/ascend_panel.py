"""Growing beyond the start: a second class and the awakening of hidden power."""

from __future__ import annotations

from ..game.data.classes import CLASSES
from ..shared.text import bold, fa
from .panel import Ctx, Screen, screen


@screen("ascend")
async def ascend(c: Ctx) -> Screen:
    b = c.services.ctx.balance
    p = await c.refresh()
    lines = [f"✨ {bold('ارتقای قهرمان')}", ""]
    rows = []
    if p.class2:
        lines += [f"🎭 کلاس دوم شما: {p.class2.emoji} {p.class2.name}", ""]
    else:
        lines += [
            f"🎭 {bold('کلاس دوم')}",
            f"از سطح {fa(b.second_class_level)} می‌توانید یک تخصص دوم برگزینید و نیمی از توان آن کلاس را به‌دست آورید.",
            f"هزینه: {fa(b.second_class_gold)} سکه",
            "",
        ]
        rows.append([c.btn("🎭 انتخاب کلاس دوم", "class2")])
    if p.awakened:
        lines += ["✨ قدرت پنهان نژادتان بیدار شده است."]
    else:
        lines += [
            f"✨ {bold('بیداری قدرت')}",
            f"از سطح {fa(b.awaken_level)} قدرت پنهان نژادتان بیدار می‌شود: بونوس نژاد دو برابر و ده درصد توان بیشتر.",
            f"هزینه: {fa(b.awaken_gold)} سکه و {fa(b.awaken_crystal)} کریستال",
        ]
        rows.append([c.btn("✨ بیدار کردن قدرت", "awakeq", style="primary")])
    rows.append(c.back("profile"))
    return Screen("\n".join(lines), rows)


@screen("class2")
async def class_two(c: Ctx) -> Screen:
    p = c.player
    options = [k for k in CLASSES.values() if k.id != p.class_id]
    text = (
        f"🎭 {bold('کلاس دوم را برگزینید')}\n\n"
        "هر کلاس توان خودش را (به‌صورت نیمه) به شما می‌دهد. انتخاب برگشت ندارد.\n\n"
        + "\n\n".join(f"{k.emoji} {k.name} — {k.description}" for k in options)
    )
    rows = [[c.btn(f"{k.emoji} {k.name}", "class2q", k.id)] for k in options]
    rows.append(c.back("ascend"))
    return Screen(text, rows)


@screen("class2q")
async def class_two_ask(c: Ctx) -> Screen:
    b = c.services.ctx.balance
    k = CLASSES[c.a]
    text = (
        f"🎭 {bold('کلاس دوم: ' + k.name)}\n\n"
        f"هزینه: {fa(b.second_class_gold)} سکه (شما {fa(c.player.gold)} دارید)\n\n"
        "این انتخاب برای همیشه است. مطمئنید؟"
    )
    return Screen(text, [[c.btn("✅ بله، انتخاب شود", "class2do", k.id, style="success"), c.btn("↩️ نه", "class2")]])


@screen("class2do")
async def class_two_do(c: Ctx) -> Screen:
    after = await c.services.characters.choose_second_class(c.player, c.a)
    c.player = after
    shown = await ascend(c)
    shown.toast, shown.alert = f"🎭 کلاس دوم شما {after.class2.name} شد!", True
    return shown


@screen("awakeq")
async def awaken_ask(c: Ctx) -> Screen:
    b = c.services.ctx.balance
    text = (
        f"✨ {bold('بیداری قدرت')}\n\n"
        f"هزینه: {fa(b.awaken_gold)} سکه و {fa(b.awaken_crystal)} کریستال\n\n"
        f"شما {fa(c.player.gold)} سکه و {fa(c.player.crystal)} کریستال دارید.\n\n"
        "قدرت نژادتان برای همیشه بیدار می‌شود. آماده‌اید؟"
    )
    return Screen(text, [[c.btn("✨ بیدار شو!", "awake", style="success"), c.btn("↩️ نه", "ascend")]])


@screen("awake")
async def awake(c: Ctx) -> Screen:
    c.player = await c.services.characters.awaken(c.player)
    shown = await ascend(c)
    shown.toast, shown.alert = "✨ قدرت پنهان شما بیدار شد!", True
    return shown

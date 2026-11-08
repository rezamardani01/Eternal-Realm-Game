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
    rows.append([c.btn("🎫 خدمات (تغییر نژاد، کلاس، نام)", "svc")])
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


# --- paid services -----------------------------------------------------------------------------------------
async def _tickets(c: Ctx) -> dict[str, int]:
    view = await c.services.inventory.view(c.player.id)
    return {i.id: q for i, q in view.stacks if i.id in ("rename_ticket", "race_ticket", "class_ticket")}


@screen("svc")
async def services_hub(c: Ctx) -> Screen:
    have = await _tickets(c)
    text = (
        f"🎫 {bold('خدمات قهرمان')}\n\n"
        "با برگه‌های خدمات می‌توانید نژاد، کلاس یا نام قهرمانتان را عوض کنید. برگه‌ها را از «خزانه‌ی ویژه» (پیام خصوصی ربات) می‌خرید.\n\n"
        f"🧬 برگه‌ی تغییر نژاد: {fa(have.get('race_ticket', 0))}\n\n"
        f"⚔️ برگه‌ی تغییر کلاس: {fa(have.get('class_ticket', 0))}\n\n"
        f"🏷️ برگه‌ی تغییر نام: {fa(have.get('rename_ticket', 0))}"
    )
    rows = [
        [c.btn("🧬 تغییر نژاد", "svcrace"), c.btn("⚔️ تغییر کلاس", "svcclass")],
        [c.btn("🏷️ تغییر نام", "svcname")],
        c.back("ascend"),
    ]
    return Screen(text, rows)


@screen("svcrace")
async def svc_race(c: Ctx) -> Screen:
    from ..game.data.races import RACES

    if not (await _tickets(c)).get("race_ticket"):
        return Screen(None, toast="🧬 برگه‌ی تغییر نژاد ندارید؛ از خزانه‌ی ویژه بخرید.", alert=True)
    options = [r for r in RACES.values() if r.id != c.player.race_id]
    text = f"🧬 {bold('نژاد تازه را انتخاب کنید')}\n\n" + "\n\n".join(f"{r.emoji} {r.name} — {r.description}" for r in options)
    rows = [[c.btn(f"{r.emoji} {r.name}", "svcraceq", r.id)] for r in options] + [c.back("svc")]
    return Screen(text, rows)


@screen("svcraceq")
async def svc_race_ask(c: Ctx) -> Screen:
    from ..game.data.races import RACES

    r = RACES[c.a]
    text = (
        f"🧬 {bold('تأیید تغییر نژاد')}\n\nاز {c.player.race.name} به {r.emoji} {r.name}\n\n"
        "یک برگه‌ی تغییر نژاد مصرف می‌شود و برگشت ندارد. مطمئنید؟"
    )
    return Screen(text, [[c.btn("✅ بله، تغییر کند", "svcracedo", r.id, style="danger"), c.btn("↩️ نه", "svcrace")]])


@screen("svcracedo")
async def svc_race_do(c: Ctx) -> Screen:
    after = await c.services.characters.change_race(c.player, c.a)
    c.player = after
    shown = await services_hub(c)
    shown.toast, shown.alert = f"🧬 نژاد شما {after.race.name} شد!", True
    return shown


@screen("svcclass")
async def svc_class(c: Ctx) -> Screen:
    if not (await _tickets(c)).get("class_ticket"):
        return Screen(None, toast="⚔️ برگه‌ی تغییر کلاس ندارید؛ از خزانه‌ی ویژه بخرید.", alert=True)
    options = [k for k in CLASSES.values() if k.id != c.player.class_id]
    text = f"⚔️ {bold('کلاس تازه را انتخاب کنید')}\n\n" + "\n\n".join(f"{k.emoji} {k.name} — {k.description}" for k in options)
    rows = [[c.btn(f"{k.emoji} {k.name}", "svcclassq", k.id)] for k in options] + [c.back("svc")]
    return Screen(text, rows)


@screen("svcclassq")
async def svc_class_ask(c: Ctx) -> Screen:
    k = CLASSES[c.a]
    text = (
        f"⚔️ {bold('تأیید تغییر کلاس')}\n\nاز {c.player.char_class.name} به {k.emoji} {k.name}\n\n"
        "یک برگه‌ی تغییر کلاس مصرف می‌شود و برگشت ندارد. مطمئنید؟"
    )
    return Screen(text, [[c.btn("✅ بله، تغییر کند", "svcclassdo", k.id, style="danger"), c.btn("↩️ نه", "svcclass")]])


@screen("svcclassdo")
async def svc_class_do(c: Ctx) -> Screen:
    after = await c.services.characters.change_class(c.player, c.a)
    c.player = after
    shown = await services_hub(c)
    shown.toast, shown.alert = f"⚔️ کلاس شما {after.char_class.name} شد!", True
    return shown


@screen("svcname")
async def svc_name(c: Ctx) -> Screen:
    text = (
        f"🏷️ {bold('تغییر نام')}\n\n"
        "نام تازه را با این فرمان بنویسید:\n«تغییر نام نام‌تازه»\n\n"
        "پیش از مصرف برگه، یک صفحه‌ی تأیید می‌بینید."
    )
    return Screen(text, [c.back("svc")])


@screen("svcnamedo")
async def svc_name_do(c: Ctx) -> Screen:
    after = await c.services.characters.rename(c.player, c.a)
    return Screen(f"🏷️ {bold('نام شما عوض شد')}\n\nاز این پس {after.name} نامیده می‌شوید.", [c.back("home", "🔙 منو")])

"""Hero war gear screens: «تجهیزات قهرمان» (the four slots), «مهارت‌ها» (the three skills) and the gear shop of the
realm treasury (reached from «خزانه قلمرو»). Everything is data from ``data/arms.py`` and ``data/skills.py``."""

from __future__ import annotations

from baleropy import Button

from ..game.data.arms import CATEGORIES, MAX_EQUIPPED, RARITIES, Arm, arms_of, get_arm, pack_id, trait_text
from ..game.data.classes import CLASSES
from ..game.data.races import RACES
from ..game.data.skills import skills_for
from ..shared.errors import GameError
from ..shared.text import bold, fa
from . import keyboards
from .callbacks import BuyCb
from .panel import Ctx, Screen, screen

LINE = "─" * 12
CIRCLED = ("①", "②", "③", "④")


def _private(c: Ctx) -> None:
    if c.is_group:
        raise GameError("تجهیزات قهرمان را در پیام خصوصی ربات تنظیم کنید.")


def _summary(worn: list[Arm]) -> list[str]:
    """What the whole loadout does, in a few lines."""
    lines = sum_stats(worn).bonus_lines() or ["هنوز تجهیزاتی ندارید"]
    seen: list[str] = []
    for arm in worn:
        for trait in arm.traits:
            text = trait_text(trait)
            if text and text not in seen:
                seen.append(text)
    return lines + seen


def sum_stats(worn: list[Arm]):  # noqa: ANN201
    from ..game.data.stats import Stats

    total = Stats()
    for arm in worn:
        total = total + arm.stats
    return total


# --- the hero's four slots ---------------------------------------------------------------------------------------------------------
@screen("arms")
async def arms(c: Ctx) -> Screen:
    _private(c)
    loadout = await c.services.arms.loadout(c.player.id)
    lines = [f"⚔️ {bold('تجهیزات قهرمان')}", LINE, f"{c.player.char_class.emoji} {c.player.name} · سطح {fa(c.player.level)}", ""]
    rows = []
    for i, arm in enumerate(loadout.slots):
        lines.append(f"{CIRCLED[i]} {arm.label if arm else '— جای خالی —'}")
        rows.append(c.btn(f"{CIRCLED[i]} {arm.label if arm else 'جای خالی'}", "armslot", f"{i + 1}.0"))
    lines += ["", f"📊 {bold('اثر تجهیزات')}", *_summary(loadout.worn), "", "🔁 بیرون از نبرد هر وقت خواستید تجهیزات را عوض کنید و بیلد تازه بسازید."]
    grid = keyboards.grid(rows, 2)
    grid.append([c.btn("🛒 خرید تجهیزات", "armshop", style="primary"), c.btn("🌟 مهارت‌های من", "skills")])
    grid.append(c.back("profile"))
    return Screen("\n".join(lines), grid)


@screen("armslot")
async def arm_slot(c: Ctx) -> Screen:
    _private(c)
    slot_s, _, page_s = c.a.partition(".")
    slot, page = int(slot_s or 1), int(page_s or 0)
    owned = await c.services.arms.owned(c.player.id)
    loadout = await c.services.arms.loadout(c.player.id)
    here = loadout.slots[slot - 1] if 1 <= slot <= MAX_EQUIPPED else None
    pieces = sorted((get_arm(i) for i in owned), key=lambda a: (-a.rarity, a.name))
    per = 8
    chunk = pieces[page * per:(page + 1) * per]
    lines = [f"{CIRCLED[slot - 1]} {bold('جایگاه ' + fa(slot))}", LINE, f"الان: {here.label if here else '— خالی —'}", ""]
    if not pieces:
        lines.append("هنوز تجهیزاتی ندارید. از «خزانه قلمرو» با سکه یا پول واقعی بخرید 🛒")
    else:
        lines.append("یکی را برای این جایگاه انتخاب کنید 👇")
    rows = []
    for arm in chunk:
        mark = "✅ " if here and here.id == arm.id else ""
        rows.append(c.btn(f"{mark}{arm.label}", "armeq", str(slot), arm.id))
    grid = keyboards.grid(rows, 2)
    nav = []
    if page > 0:
        nav.append(c.btn("⬅️ قبلی", "armslot", f"{slot}.{page - 1}"))
    if (page + 1) * per < len(pieces):
        nav.append(c.btn("بعدی ➡️", "armslot", f"{slot}.{page + 1}"))
    if nav:
        grid.append(nav)
    if here:
        grid.append([c.btn("🗑️ خالی کردن این جایگاه", "armout", str(slot), style="danger")])
    grid.append([c.btn("🛒 خرید تجهیزات", "armshop")])
    grid.append(c.back("arms"))
    return Screen("\n".join(lines), grid)


@screen("armeq")
async def arm_equip(c: Ctx) -> Screen:
    _private(c)
    arm = get_arm(c.b)
    player = await c.refresh()
    await c.services.arms.equip(player, int(c.a), c.b)
    shown = await arms(c)
    shown.toast = f"✅ {arm.name} تجهیز شد"
    return shown


@screen("armout")
async def arm_unequip(c: Ctx) -> Screen:
    _private(c)
    await c.services.arms.unequip(c.player, int(c.a))
    shown = await arms(c)
    shown.toast = "🗑️ جایگاه خالی شد"
    return shown


# --- the three skills --------------------------------------------------------------------------------------------------------------
@screen("skills")
async def skills(c: Ctx) -> Screen:
    p = c.player
    race, cls = RACES[p.race_id], CLASSES[p.class_id]
    lines = [
        f"🌟 {bold('مهارت‌های ' + p.name)}", LINE, f"{race.emoji} {race.name} · {cls.emoji} {cls.name}", "",
        "هر مهارت کار خودش را می‌کند؛ نوبت‌های انتظارشان را هنگام نبرد روی دکمه‌ها می‌بینید.", "",
    ]
    for sk in skills_for(p.race_id, p.class_id):
        lines += [f"{sk.emoji} {bold(f'مهارت {fa(sk.slot)}: {sk.name}')}", *[f"   {line}" for line in sk.describe()], ""]
    lines.append("🧠 ترکیب مهارت‌ها و چهار تجهیزات شما تعیین می‌کند نبرد چطور پیش برود.")
    rows = [[c.btn("⚔️ تجهیزات قهرمان", "arms")] if not c.is_group else [], c.back("profile")]
    return Screen("\n".join(lines), [r for r in rows if r])


# --- the shop of the realm treasury ----------------------------------------------------------------------------------------------
@screen("armshop")
async def arm_shop(c: Ctx) -> Screen:
    _private(c)
    p = await c.refresh()
    owned = await c.services.arms.owned(p.id)
    lines = [
        f"🛒 {bold('تجهیزات جنگی')}", LINE, f"👛 کیف شما: {fa(p.gold)} سکه", "",
        "همه‌ی تجهیزات را هم با سکه‌ی بازی می‌توانید بخرید، هم با پول واقعی؛ هر دو راه یک تجهیزات را می‌دهند.",
        "هر تعداد که بخواهید می‌توانید بخرید، اما فقط ۴ تا را هم‌زمان روی قهرمان می‌گذارید. 👇",
    ]
    rows = [
        c.btn(f"{emoji} {title}", "armcat", cat)
        for cat, (emoji, title) in CATEGORIES.items()
    ]
    grid = keyboards.grid(rows, 2)
    grid.append([c.btn(f"🎒 تجهیزات من ({fa(sum(owned.values()))})", "arms")])
    grid.append(c.back("premium"))
    return Screen("\n".join(lines), grid)


@screen("armcat")
async def arm_category(c: Ctx) -> Screen:
    _private(c)
    emoji, title = CATEGORIES[c.a]
    owned = await c.services.arms.owned(c.player.id)
    lines = [f"{emoji} {bold(title)}", LINE, "یکی را بزنید تا ویژگی‌هایش را ببینید 👇", ""]
    rows = []
    for arm in arms_of(c.a):
        have = f" · ×{fa(owned[arm.id])}" if arm.id in owned else ""
        lines.append(f"{RARITIES[arm.rarity][0]} {arm.label} — 🪙 {fa(arm.price)}{have}")
        rows.append(c.btn(f"{RARITIES[arm.rarity][0]} {arm.name}", "armview", arm.id))
    grid = keyboards.grid(rows, 2)
    grid.append(c.back("armshop"))
    return Screen("\n".join(lines), grid)


def _card_buttons(c: Ctx, arm: Arm, have: int) -> list[list]:
    rows = [[c.btn(f"🪙 خرید با سکه ({fa(arm.price)})", "armbuy", arm.id, style="success")]]
    rows.append([Button.inline(f"💳 خرید با پول واقعی ({fa(arm.rial // 10)} تومان)", BuyCb(kind="cash", id=pack_id(arm.id)))])
    if have:
        rows.append([c.btn("✅ تجهیز کردن", "armput", arm.id, style="primary")])
    rows.append(c.back("armcat", "↩️ بازگشت", arm.cat))
    return rows


@screen("armview")
async def arm_view(c: Ctx) -> Screen:
    _private(c)
    arm = get_arm(c.a)
    p = await c.refresh()
    have = (await c.services.arms.owned(p.id)).get(arm.id, 0)
    text = f"{arm.card()}\n\n{LINE}\n💰 قیمت: {fa(arm.price)} سکه\n👛 کیف شما: {fa(p.gold)} سکه"
    if have:
        text += f"\n🎒 در کیف شما: ×{fa(have)}"
    return Screen(text, _card_buttons(c, arm, have))


@screen("armbuy")
async def arm_buy(c: Ctx) -> Screen:
    _private(c)
    arm = await c.services.arms.buy(c.player, c.a)
    shown = await arm_view(c)
    shown.toast = f"✅ {arm.name} خریداری شد"
    return shown


@screen("armput")
async def arm_put(c: Ctx) -> Screen:
    """Pick the place where a piece you own should go."""
    _private(c)
    arm = get_arm(c.a)
    loadout = await c.services.arms.loadout(c.player.id)
    lines = [f"✅ {bold('تجهیز ' + arm.name)}", LINE, "در کدام جایگاه بگذاریم؟"]
    rows = [
        c.btn(f"{CIRCLED[i]} {slot.label if slot else 'خالی'}", "armeq", str(i + 1), arm.id)
        for i, slot in enumerate(loadout.slots)
    ]
    grid = keyboards.grid(rows, 2)
    grid.append(c.back("armview", "↩️ بازگشت", arm.id))
    return Screen("\n".join(lines), grid)


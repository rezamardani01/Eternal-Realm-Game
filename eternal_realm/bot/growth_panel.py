"""Hero growth screens: attribute points, class talents, the level road, and the upgrade of war gear."""

from __future__ import annotations

from ..game.data.arms import MAX_UPGRADE, UPGRADE_CHANCE, get_arm, plus, upgrade_gold, upgrade_materials, upgraded_stats
from ..game.data.growth import (
    ATTRS, POINTS_PER_LEVEL, TALENT_LEVELS, UNLOCKS, attr_effect_text, next_unlock,
    points_earned, talent_places,
)
from ..game.data.items import get_item
from ..shared.errors import GameError
from ..shared.text import bar, bold, fa
from . import keyboards
from .panel import Ctx, Screen, screen

LINE = "─" * 12


def _private(c: Ctx) -> None:
    if c.is_group:
        raise GameError("این بخش را در پیام خصوصی ربات باز کنید.")


# --- the road of levels ------------------------------------------------------------------------------------------------------------
@screen("progress")
async def progress(c: Ctx) -> Screen:
    _private(c)
    p = await c.refresh()
    need = c.services.characters.xp_needed(p)
    free = await c.services.growth.free_points(p)
    lines = [f"📈 {bold('راه پیشرفت')}", LINE, f"⭐ سطح {fa(p.level)}", f"{bar(p.xp, need, 12)} {fa(p.xp)} / {fa(need)} تجربه"]
    gap = max(0, need - p.xp)
    lines.append(f"🎯 {fa(gap)} تجربه تا سطح {fa(p.level + 1)}")
    lines += ["", "💡 تجربه از نبرد، شکار، باس‌ها، سفر قهرمان و مأموریت‌ها می‌آید.", "",
              f"🎁 هر سطح {fa(POINTS_PER_LEVEL)} امتیاز ویژگی می‌دهد؛ الان {bold(fa(free))} امتیاز آماده دارید."]
    nxt = next_unlock(p.level)
    if nxt:
        lines.append(f"🔓 بعدی: سطح {fa(nxt[0])} — {nxt[1]} {nxt[2]}")
    lines += ["", f"🗺️ {bold('بازشدن‌ها')}"]
    for need_level, emoji, title, text in UNLOCKS:
        mark = "✅" if p.level >= need_level else "🔒"
        lines.append(f"{mark} سطح {fa(need_level)} · {emoji} {title}")
    rows = [[c.btn("🎯 ویژگی‌ها", "attrs", style="primary"), c.btn("🧬 استعدادها", "talents")], c.back("arms")]
    return Screen("\n".join(lines), rows)


# --- attributes -------------------------------------------------------------------------------------------------------------------
@screen("attrs")
async def attrs(c: Ctx) -> Screen:
    _private(c)
    p = await c.refresh()
    mine = await c.services.growth.attrs(p.id)
    free = max(0, points_earned(p.level) - sum(mine.values()))
    lines = [
        f"🎯 {bold('ویژگی‌های قهرمان')}", LINE,
        f"🎁 امتیاز آماده: {bold(fa(free))} (هر سطح {fa(POINTS_PER_LEVEL)} امتیاز)", "",
        "امتیازها را خودتان خرج می‌کنید؛ پس دو قهرمانِ هم‌کلاس می‌توانند کاملاً متفاوت شوند.", "",
    ]
    rows = []
    for attr in ATTRS.values():
        lines.append(f"{attr.emoji} {bold(attr.name)}: {fa(mine.get(attr.id, 0))}")
        lines.append(f"   {attr.blurb} · هر امتیاز: {attr_effect_text(attr)}")
        rows.append([
            c.btn(f"{attr.emoji} {attr.name} · {fa(mine.get(attr.id, 0))}  ➕", "attradd", attr.id, "1", style="success" if free else None),
            c.btn("➕۵", "attradd", attr.id, "5"),
        ])
    if sum(mine.values()):
        rows.append([c.btn(f"♻️ بازتقسیم ({fa(c.services.growth.reset_price(p))} سکه)", "attrresetq", style="danger")])
    rows.append(c.back("progress"))
    return Screen("\n".join(lines), rows)


@screen("attradd")
async def attr_add(c: Ctx) -> Screen:
    _private(c)
    await c.services.growth.spend(c.player, c.a, int(c.b or 1))
    shown = await attrs(c)
    shown.toast = "✅ امتیاز خرج شد"
    return shown


@screen("attrresetq")
async def attr_reset_ask(c: Ctx) -> Screen:
    _private(c)
    price = c.services.growth.reset_price(c.player)
    text = (
        f"♻️ {bold('بازتقسیم امتیازها')}\n\nهمه‌ی امتیازهایتان برمی‌گردد و می‌توانید دوباره تقسیمشان کنید.\n"
        f"💰 هزینه: {fa(price)} سکه"
    )
    return Screen(text, [[c.btn("✅ بله، بازتقسیم", "attrreset", style="danger"), c.btn("↩️ نه", "attrs")]])


@screen("attrreset")
async def attr_reset(c: Ctx) -> Screen:
    _private(c)
    back = await c.services.growth.reset(c.player)
    shown = await attrs(c)
    shown.toast = f"♻️ {fa(back)} امتیاز برگشت"
    return shown


# --- talents ---------------------------------------------------------------------------------------------------------------------
@screen("talents")
async def talents(c: Ctx) -> Screen:
    _private(c)
    p = await c.refresh()
    chosen = await c.services.growth.talents(p)
    places = talent_places(p.level)
    lines = [f"🧬 {bold('استعدادهای ' + p.char_class.name)}", LINE]
    if places:
        lines.append(f"جای استعداد: {fa(len(chosen))} از {fa(places)} پر است")
    else:
        lines.append(f"🔒 استعدادها از سطح {fa(TALENT_LEVELS[0])} باز می‌شوند")
    lines += ["همه را نمی‌شود هم‌زمان داشت؛ انتخاب کنید و هر وقت خواستید (بیرون از نبرد) عوضشان کنید.", ""]
    rows = []
    for t in c.services.growth.available(p):
        on = t.id in chosen
        lines += [f"{'✅' if on else '▫️'} {t.label}: {t.blurb}", *[f"     {line}" for line in t.lines()]]
        rows.append(c.btn(f"{'✅ ' if on else ''}{t.label}", "talent", t.id))
    grid = keyboards.grid(rows, 2)
    grid.append(c.back("progress"))
    return Screen("\n".join(lines), grid)


@screen("talent")
async def talent_toggle(c: Ctx) -> Screen:
    _private(c)
    p = await c.refresh()
    if c.a in await c.services.growth.talents(p):
        await c.services.growth.drop(p, c.a)
        toast = "↩️ استعداد برداشته شد"
    else:
        await c.services.growth.choose(p, c.a)
        toast = "✅ استعداد فعال شد"
    shown = await talents(c)
    shown.toast = toast
    return shown


# --- upgrading war gear -----------------------------------------------------------------------------------------------------------
@screen("armup")
async def arm_upgrade(c: Ctx) -> Screen:
    _private(c)
    arm = get_arm(c.a)
    p = await c.refresh()
    owned = await c.services.arms.owned(p.id)
    if arm.id not in owned:
        raise GameError("این تجهیزات را ندارید.")
    level = (await c.services.arms.plus_of(p.id)).get(arm.id, 0)
    lines = [f"⬆️ {bold('ارتقای ' + arm.name)} {plus(level)}", LINE]
    if level >= MAX_UPGRADE:
        lines.append(f"✨ به بیشترین ارتقا (+{fa(MAX_UPGRADE)}) رسیده است.")
        return Screen("\n".join(lines), [c.back("armview", "↩️ بازگشت", arm.id)])
    target = level + 1
    now_stats, next_stats = upgraded_stats(arm, level), upgraded_stats(arm, target)
    lines += [f"الان: {plus(level) or '+۰'}  ←  بعد: {plus(target)}", ""]
    for key, label in (("atk", "⚔️ حمله"), ("defense", "🛡️ دفاع"), ("hp", "❤️ جان"), ("magic", "✨ جادو"), ("speed", "💨 سرعت"), ("luck", "🍀 شانس")):
        before, after = getattr(now_stats, key), getattr(next_stats, key)
        if after:
            lines.append(f"{label}: {fa(before)} ← {bold(fa(after))}")
    gold, mats = upgrade_gold(arm, target), upgrade_materials(target)
    lines += ["", f"🎲 شانس موفقیت: {fa(round(UPGRADE_CHANCE[target - 1] * 100))}٪", f"💰 هزینه: {fa(gold)} سکه (👛 {fa(p.gold)})", "📦 منابع:"]
    stock = {item.id: n for item, n in (await c.services.inventory.view(p.id)).stacks}
    for item_id, qty in mats.items():
        lines.append(f"   {get_item(item_id).label} ×{fa(qty)} (دارید {fa(stock.get(item_id, 0))})")
    lines += ["", "⚠️ اگر شکست بخورد، سکه و منابع از دست می‌رود و سطح ارتقا همان می‌ماند."]
    return Screen("\n".join(lines), [[c.btn("⬆️ تلاش برای ارتقا", "armupgo", arm.id, style="success")], c.back("armview", "↩️ بازگشت", arm.id)])


@screen("armupgo")
async def arm_upgrade_go(c: Ctx) -> Screen:
    _private(c)
    result = await c.services.arms.upgrade(c.player, c.a)
    shown = await arm_upgrade(c)
    if result.success:
        shown.toast = f"✨ ارتقا موفق بود! {result.arm.name} {plus(result.level)}"
    else:
        shown.toast = "💥 ارتقا شکست خورد؛ سطح همان ماند."
    shown.alert = True
    return shown

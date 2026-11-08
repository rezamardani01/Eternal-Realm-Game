"""Dungeon screens: enter, walk room by room, collect the treasure."""

from __future__ import annotations

from ..game.services.dungeon import COOLDOWN, ENERGY_COST, ROOMS, RunView, loot_lines
from ..shared.text import bar, bold, duration, fa
from .panel import Ctx, Screen, screen


def _status(v: RunView) -> list[str]:
    lines = [
        f"❤️ جان: {fa(v.hp)} از {fa(v.max_hp)}",
        bar(v.hp, v.max_hp, 10),
        f"🚪 اتاق‌های رفته: {fa(v.stage)} از {fa(ROOMS)}",
    ]
    if v.gold or v.xp or v.items:
        lines += ["", f"🎒 گنج جمع‌شده: {fa(v.gold)} سکه · {fa(v.xp)} تجربه"]
        lines += loot_lines(v.items)
    return lines


@screen("dungeon")
async def dungeon(c: Ctx) -> Screen:
    run = await c.services.dungeon.current(c.player.id)
    if run is not None:
        text = f"🕳️ {bold('سیاه‌چال')}\n\nدر عمق تاریکی ایستاده‌اید...\n\n" + "\n".join(_status(run))
        rows = [[c.btn("🚪 اتاق بعدی", "dgo", style="primary")], [c.btn("🏃 فرار از سیاه‌چال", "dgoutq")], c.back("home")]
        return Screen(text, rows)
    text = (
        f"🕳️ {bold('سیاه‌چال')}\n\n"
        f"پنج اتاق پشت‌سرهم؛ در هر کدام هیولایی یا اتفاقی عجیب منتظر است و در آخر، {bold('نگهبان سیاه‌چال')}.\n\n"
        "جانتان از اتاقی به اتاق دیگر همراهتان می‌ماند. اگر بیفتید، نصف گنج را نگه می‌دارید؛ "
        "اگر نگهبان را شکست بدهید، همه‌ی گنج و یک صندوقچه‌ی جادویی مال شماست.\n\n"
        f"⚡ هزینه‌ی ورود: {fa(ENERGY_COST)} انرژی\n\n"
        f"⏳ هر {duration(COOLDOWN)} یک بار"
    )
    return Screen(text, [[c.btn("🕳️ ورود به سیاه‌چال", "dgenterq", style="success")], c.back("home")])


@screen("dgenterq")
async def enter_ask(c: Ctx) -> Screen:
    p = await c.refresh()
    top = c.services.characters.max_energy(p)
    text = (
        f"🕳️ {bold('تأیید ورود')}\n\n"
        f"ورود {fa(ENERGY_COST)} انرژی می‌خواهد. انرژی شما حدود {fa(p.energy)} از {fa(top)} است.\n\n"
        "جان کامل شما در همه‌ی اتاق‌ها مصرف می‌شود، پس آماده باشید. وارد شویم؟"
    )
    return Screen(text, [[c.btn("✅ بله، وارد شو", "dgenter", style="success"), c.btn("↩️ نه", "dungeon")]])


@screen("dgenter")
async def enter(c: Ctx) -> Screen:
    await c.services.dungeon.enter(c.player)
    await c.show(f"🕳️ {bold('ورود به سیاه‌چال')}\n\nدروازه‌ی سنگی پشت سرتان بسته می‌شود...")
    shown = await dungeon(c)
    shown.toast = "🕳️ وارد شدید!"
    return shown


@screen("dgo")
async def go(c: Ctx) -> Screen:
    await c.show(f"🚪 {bold('در حال گشودن در')}\n\nقدم به اتاق بعدی می‌گذارید...")
    v = await c.services.dungeon.advance(c.player)
    lines = [f"{v.emoji} {bold(v.title)}", "", *v.lines, ""]
    if v.status == "active":
        lines += _status(v)
        rows = [[c.btn("🚪 اتاق بعدی", "dgo", style="primary")], [c.btn("🏃 فرار", "dgoutq")]]
        return Screen("\n".join(lines), rows)
    if v.status == "won":
        lines += [
            f"🏆 {bold('سیاه‌چال فتح شد!')}",
            "",
            f"🪙 {fa(v.paid_gold)} سکه",
            f"⭐ {fa(v.paid_xp)} تجربه",
            *loot_lines(v.items),
        ]
    else:
        lines += [
            f"💀 {bold('شکست خوردید')}",
            "",
            f"نصف گنج را نگه داشتید: {fa(v.paid_gold)} سکه و {fa(v.paid_xp)} تجربه.",
            "قوی‌تر شوید و دوباره بیایید!",
        ]
    if v.level_up:
        lines += ["", f"🎉 رسیدید به سطح {fa(v.level_up)}"]
    return Screen("\n".join(lines), [c.back("home", "🔙 منو")])


@screen("dgoutq")
async def out_ask(c: Ctx) -> Screen:
    text = f"🏃 {bold('فرار از سیاه‌چال')}\n\nاگر فرار کنید، گنجی که جمع کرده‌اید از دست می‌رود. مطمئنید؟"
    return Screen(text, [[c.btn("🏃 بله، فرار", "dgout", style="danger"), c.btn("↩️ نه", "dungeon")]])


@screen("dgout")
async def out(c: Ctx) -> Screen:
    await c.services.dungeon.leave(c.player)
    return Screen(f"🏃 {bold('از سیاه‌چال گریختید')}\n\nسالم برگشتید، اما دست‌خالی.", [c.back("home", "🔙 منو")])

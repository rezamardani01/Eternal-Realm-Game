"""Dungeon screens: enter, walk room by room, collect the treasure."""

from __future__ import annotations

from ..game.services.dungeon import COOLDOWN, ENERGY_COST, ROOMS, RunView, loot_lines
from ..shared.text import bar, bold, duration, fa
from .panel import Ctx, Screen, screen


def _status(v: RunView) -> list[str]:
    lines = [
        f"❤️ جان شما: {fa(v.hp)} از {fa(v.max_hp)}",
        bar(v.hp, v.max_hp, 10),
        f"🚪 اتاق‌هایی که رد کرده‌اید: {fa(v.stage)} از {fa(ROOMS)}",
    ]
    if v.gold or v.xp or v.items:
        lines += ["", f"🎒 گنجی که تا الان دارید: {fa(v.gold)} سکه و {fa(v.xp)} تجربه"]
        lines += loot_lines(v.items)
    return lines


@screen("dungeon")
async def dungeon(c: Ctx) -> Screen:
    run = await c.services.dungeon.current(c.player.id)
    if run is not None:
        text = (
            f"🕳️ {bold('شما توی سیاه‌چال هستید')}\n\n"
            "جلوی شما یک در بسته است. هر بار که «اتاق بعدی» را بزنید، در باز می‌شود و یک اتفاق می‌افتد.\n\n"
            + "\n".join(_status(run))
            + "\n\nاگر جانتان تمام شود، نصف گنج را نگه می‌دارید. اگر فرار کنید، گنج را از دست می‌دهید."
        )
        rows = [[c.btn("🚪 اتاق بعدی", "dgo", style="primary")], [c.btn("🏃 فرار از سیاه‌چال", "dgoutq")], c.back("home")]
        return Screen(text, rows)
    text = (
        f"🕳️ {bold('سیاه‌چال')}\n\n"
        "سیاه‌چال یک غار تاریک با پنج اتاق است. شما اتاق‌ها را یکی‌یکی رد می‌کنید.\n\n"
        f"{bold('در هر اتاق یکی از این‌ها پیش می‌آید:')}\n"
        "👹 یک هیولا؛ با او می‌جنگید\n"
        "💰 یک صندوق گنج؛ سکه پیدا می‌کنید\n"
        "🪤 یک تله؛ کمی از جانتان کم می‌شود\n"
        "⛲ یک چشمه؛ جانتان پر می‌شود\n"
        "🕯️ یک محراب؛ یک برکت یا نفرین می‌گیرید\n\n"
        f"👑 اتاق پنجم همیشه {bold('نگهبان سیاه‌چال')} است؛ او قوی‌ترین است!\n\n"
        f"{bold('قانون‌ها:')}\n"
        "❤️ جانتان بین اتاق‌ها پر نمی‌شود، پس مواظب باشید\n"
        "🏆 اگر نگهبان را شکست بدهید، همه‌ی گنج و یک صندوقچه‌ی جادویی می‌گیرید\n"
        "💔 اگر جانتان تمام شود، نصف گنج را نگه می‌دارید\n\n"
        f"⚡ ورود {fa(ENERGY_COST)} انرژی می‌خواهد و هر {duration(COOLDOWN)} یک بار می‌شود وارد شد."
    )
    return Screen(text, [[c.btn("🕳️ ورود به سیاه‌چال", "dgenterq", style="success")], c.back("home")])


@screen("dgenterq")
async def enter_ask(c: Ctx) -> Screen:
    p = await c.refresh()
    top = c.services.characters.max_energy(p)
    text = (
        f"🕳️ {bold('تأیید ورود')}\n\n"
        f"برای ورود {fa(ENERGY_COST)} انرژی خرج می‌شود. انرژی شما الان {fa(p.energy)} از {fa(top)} است.\n\n"
        "یادتان باشد: جانتان بین اتاق‌ها پر نمی‌شود. آماده‌اید؟"
    )
    return Screen(text, [[c.btn("✅ بله، وارد شو", "dgenter", style="success"), c.btn("↩️ نه", "dungeon")]])


@screen("dgenter")
async def enter(c: Ctx) -> Screen:
    await c.services.dungeon.enter(c.player)
    await c.show(f"🕳️ {bold('وارد شدید')}\n\nدروازه‌ی سنگی پشت سرتان بسته شد. همه‌جا تاریک است...")
    shown = await dungeon(c)
    shown.toast = "🕳️ وارد شدید!"
    return shown


@screen("dgo")
async def go(c: Ctx) -> Screen:
    await c.show(f"🚪 {bold('در حال باز کردن در')}\n\nآرام آرام وارد اتاق بعدی می‌شوید...")
    v = await c.services.dungeon.advance(c.player)
    lines = [f"{v.emoji} {bold(v.title)}", "", *v.lines, ""]
    if v.status == "active":
        lines += _status(v)
        rows = [[c.btn("🚪 اتاق بعدی", "dgo", style="primary")], [c.btn("🏃 فرار", "dgoutq")]]
        return Screen("\n".join(lines), rows)
    if v.status == "won":
        lines += [
            f"🏆 {bold('آفرین! سیاه‌چال را فتح کردید!')}",
            "",
            "نگهبان را شکست دادید و این‌ها مال شماست:",
            f"🪙 {fa(v.paid_gold)} سکه",
            f"⭐ {fa(v.paid_xp)} تجربه",
            *loot_lines(v.items),
        ]
    else:
        lines += [
            f"💀 {bold('جانتان تمام شد')}",
            "",
            f"اشکالی ندارد! نصف گنج را نگه داشتید: {fa(v.paid_gold)} سکه و {fa(v.paid_xp)} تجربه.",
            "قوی‌تر شوید، تجهیزاتتان را بهتر کنید و دوباره بیایید.",
        ]
    if v.level_up:
        lines += ["", f"🎉 رسیدید به سطح {fa(v.level_up)}"]
    return Screen("\n".join(lines), [c.back("home", "🔙 منو")])


@screen("dgoutq")
async def out_ask(c: Ctx) -> Screen:
    text = f"🏃 {bold('فرار از سیاه‌چال')}\n\nاگر فرار کنید، از سیاه‌چال بیرون می‌روید و گنجی که جمع کرده‌اید را از دست می‌دهید. مطمئنید؟"
    return Screen(text, [[c.btn("🏃 بله، فرار", "dgout", style="danger"), c.btn("↩️ نه", "dungeon")]])


@screen("dgout")
async def out(c: Ctx) -> Screen:
    await c.services.dungeon.leave(c.player)
    return Screen(f"🏃 {bold('از سیاه‌چال بیرون آمدید')}\n\nسالم هستید، اما گنجی نبردید. هر وقت آماده بودید دوباره بیایید.", [c.back("home", "🔙 منو")])

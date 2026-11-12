"""The wheel of fortune in the treasury: buy spins, watch the wheel turn, collect the prize."""

from __future__ import annotations

import contextlib
import random

from baleropy import Button
from baleropy.exceptions import BaleAPIError

from ..game.data import wheel as data
from ..game.data.packs import PACKS
from ..shared.text import bold, fa, headline
from .callbacks import BuyCb
from .panel import Ctx, Screen, screen

SPIN_PACKS = ("wheel_1", "wheel_2", "wheel_5", "wheel_10", "wheel_25", "wheel_50")


def _strip(center: str, rng: random.Random) -> str:
    """Five symbols of the wheel with the pointer above the middle one."""
    around = [rng.choice(data.SLICES).emoji for _ in range(data.STRIP - 1)]
    cells = around[: data.STRIP // 2] + [center] + around[data.STRIP // 2 :]
    return "\n".join(["            🔻", "   " + "   ".join(cells), "            🔺"])


async def _frame(c: Ctx, title: str, strip: str, factor: float) -> None:
    if c.message is not None:
        with contextlib.suppress(BaleAPIError):
            await c.message.edit_text(headline(f"🎡 {bold(title)}\n\n{strip}"))
        await c.services.ctx.pause(factor)


@screen("wheel")
async def wheel(c: Ctx) -> Screen:
    if c.is_group:
        from .panel import premium

        return await premium(c)
    p = await c.refresh()
    spins = await c.services.wheel.spins(p.id)
    free = await c.services.wheel.free_ready(p.id)
    enabled = c.services.ctx.settings.payments_enabled
    lines = [
        f"🎡 {bold('گردونه شانس')}",
        "",
        "هر چرخش یک جایزه‌ی ارزشمند دارد:",
        "🎁 صندوقچه‌های جادویی و سلطنتی",
        "🐉 فلس اژدها و پاره‌کریستال",
        "💎 تا ۱۵۰ کریستال",
        "🏦 تا ۱۵۰٬۰۰۰ سکه",
        "🔥 فلس اژدها و پاره‌کریستال‌های سنگین برای قدرتمندان",
        "",
        "🍀 هیچ چرخشی پوچ نیست؛ هر بار جایزه می‌گیرید!",
        "",
        f"🎟️ فرصت‌های شما: {bold(fa(spins))}",
        "🎁 هر روز یک چرخش رایگان دارید!" if free else "🎁 چرخش رایگان امروز را برداشته‌اید؛ فردا دوباره",
    ]
    rows = []
    if free:
        rows.append([c.btn("🎁 چرخش رایگان امروز", "wheelspin", "free", style="primary")])
    if spins:
        rows.append([c.btn(f"🎡 بچرخان ({fa(spins)} فرصت)", "wheelspin", style="success")])
    if enabled:
        lines += ["", f"🛒 {bold('خرید فرصت')}"]
        one = PACKS[SPIN_PACKS[0]]
        for pid in SPIN_PACKS:
            pack = PACKS[pid]
            save = round(100 * (1 - pack.price_rial / (pack.spins * one.price_rial)))
            lines.append(
                f"🎡 {fa(pack.spins)} فرصت · {fa(pack.price_toman)} تومان"
                + (f" ({fa(save)}٪ ارزان‌تر)" if save else "")
            )
            rows.append([Button.inline(f"🎡 {fa(pack.spins)} فرصت — {fa(pack.price_toman)} تومان", BuyCb(kind="cash", id=pid), style="primary")])
        lines += ["", "👇 یک بسته را بزنید؛ فاکتور پرداخت بله برایتان می‌آید"]
    else:
        lines += ["", "🔒 خرید فرصت فعلاً بسته است."]
    rows.append([c.btn("📋 جایزه‌ها و شانس‌ها", "wheelodds")])
    rows.append(c.back("premium"))
    return Screen("\n".join(lines), rows)


@screen("wheelodds")
async def wheel_odds(c: Ctx) -> Screen:
    lines = [f"📋 {bold('جایزه‌ها و شانس‌ها')}", ""]
    for s, share in sorted(data.odds(), key=lambda x: -x[1]):
        lines.append(f"{s.emoji} {data.describe(s)} — {fa(f'{share * 100:.1f}').replace('.', '٫')}٪")
    return Screen("\n".join(lines), [c.back("wheel")])


@screen("wheelspin")
async def wheel_spin(c: Ctx) -> Screen:
    free = c.a == "free"
    prize, left = await c.services.wheel.spin(c.player, free=free)
    rng = random.Random()
    # the wheel gathers speed, slows down, and stops on the prize
    for title, factor in (
        ("گردونه می‌چرخد…", 0.5), ("سریع‌تر…", 0.5), ("دارد کند می‌شود…", 0.8), ("چند لحظه‌ی دیگر…", 1.1),
    ):
        await _frame(c, title, _strip(rng.choice(data.SLICES).emoji, rng), factor)
    await _frame(c, "ایستاد!", _strip(prize.emoji, rng), 1.2)
    final = _strip(prize.emoji, rng)
    verdict = [
        f"🎊 {bold('جکپات!!! جایزه‌ی بزرگ!')}" if prize.jackpot else f"🎉 {bold('تبریک فرمانده!')}",
        f"🏆 جایزه: {bold(data.describe(prize))}",
        "✅ به کیف شما رسید",
    ]
    lines = [f"🎡 {bold('گردونه شانس')}", "", final, "", *verdict, ""]
    lines.append(f"🎟️ فرصت باقی‌مانده: {fa(left)}" if left or not free else "🎁 فردا دوباره بیایید؛ هر روز یک چرخش رایگان دارید")
    rows = []
    if free and not left:
        rows.append(c.back("wheel", "🔙 گردونه شانس"))
        return Screen("\n".join(lines), rows)
    if left:
        rows.append([c.btn(f"🎡 چرخاندن دوباره ({fa(left)} فرصت)", "wheelspin", style="success")])
    else:
        rows.append([c.btn("🛒 خرید فرصت تازه", "wheel", style="primary")])
    rows.append(c.back("wheel", "🔙 گردونه شانس"))
    return Screen("\n".join(lines), rows)

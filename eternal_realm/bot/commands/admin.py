"""Owner/admin tools. Private chat only, and silent for everybody else."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from baleropy.exceptions import BaleAPIError

from ...game.data.items import find_item
from ...shared.errors import GameError
from ...shared.text import fa, to_int
from .context import CommandContext
from .registry import command

_OPTIONS = {"needs_player": False, "group": False, "always_on": True, "points": 0, "category": "🛠️ مدیریت"}

HELP = """🛠️ پنل مدیریت
/stats — آمار بازی و فروش
/givegold <نام> <مقدار> — دادن سکه
/givecrystal <نام> <مقدار> — دادن کریستال
/giveitem <نام> | <آیتم> | <تعداد> — دادن آیتم
/setlevel <نام> <سطح> — تغییر سطح
/ban <نام> و /unban <نام> — مسدود/آزاد کردن بازیکن
/broadcast <متن> — پیام به همه گروه‌های فعال
/backup — نسخه پشتیبان از دیتابیس
همه این کارها در جدول admin_log ثبت می‌شوند."""


def _is_admin(ctx: CommandContext) -> bool:
    return ctx.services.ctx.settings.is_admin(ctx.user.id)


def _name_and_number(ctx: CommandContext) -> tuple[str, int]:
    number = to_int(ctx.args[-1]) if len(ctx.args) >= 2 else None
    if number is None:
        raise GameError("فرمت: /دستور <نام بازیکن> <عدد>")
    return " ".join(ctx.args[:-1]), number


@command("admin_panel", ["admin"], "راهنمای دستورهای مدیریتی (متنی)", **_OPTIONS)
async def admin_panel(ctx: CommandContext) -> None:
    if _is_admin(ctx):
        await ctx.reply(HELP)


@command("admin_stats", ["stats"], "آمار", **_OPTIONS)
async def admin_stats(ctx: CommandContext) -> None:
    if not _is_admin(ctx):
        return
    s = await ctx.services.admin.stats()
    await ctx.reply(
        "📊 آمار قلمرو جاودان\n"
        f"👥 بازیکنان: {fa(s.players)}\n🏰 گروه‌ها: {fa(s.groups)}\n⚔️ دوئل‌های جاری: {fa(s.active_duels)}\n"
        f"🛍️ سفارش‌های تحویل‌شده: {fa(s.orders)}\n💵 فروش: {fa(s.revenue_rial // 10)} تومان\n"
        f"🪙 سکه در گردش: {fa(s.gold_in_circulation)}"
    )


@command("admin_givegold", ["givegold"], "دادن سکه", takes_args=True, **_OPTIONS)
async def give_gold(ctx: CommandContext) -> None:
    if not _is_admin(ctx):
        return
    name, amount = _name_and_number(ctx)
    player = await ctx.services.admin.give_currency(ctx.user.id, name, gold=amount)
    await ctx.reply(f"✅ {fa(amount)} سکه به {player.name} داده شد.")


@command("admin_givecrystal", ["givecrystal"], "دادن کریستال", takes_args=True, **_OPTIONS)
async def give_crystal(ctx: CommandContext) -> None:
    if not _is_admin(ctx):
        return
    name, amount = _name_and_number(ctx)
    player = await ctx.services.admin.give_currency(ctx.user.id, name, crystal=amount)
    await ctx.reply(f"✅ {fa(amount)} کریستال به {player.name} داده شد.")


@command("admin_giveitem", ["giveitem"], "دادن آیتم", takes_args=True, **_OPTIONS)
async def give_item(ctx: CommandContext) -> None:
    if not _is_admin(ctx):
        return
    parts = [p.strip() for p in ctx.raw_args.split("|")]
    if len(parts) != 3 or (qty := to_int(parts[2])) is None:
        raise GameError("فرمت: /giveitem <نام بازیکن> | <نام آیتم> | <تعداد>")
    item = find_item(parts[1])
    if item is None:
        raise GameError("چنین آیتمی پیدا نشد.")
    player = await ctx.services.admin.give_item(ctx.user.id, parts[0], item, qty)
    await ctx.reply(f"✅ {item.label} ×{fa(qty)} به {player.name} داده شد.")


@command("admin_setlevel", ["setlevel"], "تغییر سطح", takes_args=True, **_OPTIONS)
async def set_level(ctx: CommandContext) -> None:
    if not _is_admin(ctx):
        return
    name, level = _name_and_number(ctx)
    player = await ctx.services.admin.set_level(ctx.user.id, name, level)
    await ctx.reply(f"✅ سطح {player.name} روی {fa(level)} تنظیم شد.")


@command("admin_ban", ["ban"], "مسدود کردن", takes_args=True, **_OPTIONS)
async def ban(ctx: CommandContext) -> None:
    if not _is_admin(ctx):
        return
    player = await ctx.services.admin.set_ban(ctx.user.id, ctx.raw_args, True)
    await ctx.reply(f"⛔ {player.name} مسدود شد.")


@command("admin_unban", ["unban"], "آزاد کردن", takes_args=True, **_OPTIONS)
async def unban(ctx: CommandContext) -> None:
    if not _is_admin(ctx):
        return
    player = await ctx.services.admin.set_ban(ctx.user.id, ctx.raw_args, False)
    await ctx.reply(f"✅ {player.name} آزاد شد.")


@command("admin_broadcast", ["broadcast"], "پیام همگانی به گروه‌ها", takes_args=True, **_OPTIONS)
async def broadcast(ctx: CommandContext) -> None:
    if not _is_admin(ctx):
        return
    text = ctx.raw_args.strip()
    if not text:
        raise GameError("فرمت: /broadcast <متن پیام>")
    sent = failed = 0
    for chat_id in await ctx.services.admin.group_ids():
        try:
            await ctx.bot.send_message(chat_id, f"📢 {text}")
            sent += 1
        except BaleAPIError:
            failed += 1
        await asyncio.sleep(0.2)  # stay far below Bale's rate limits
    await ctx.services.admin.log_action(ctx.user.id, "broadcast", f"{sent} ok / {failed} failed: {text[:80]}")
    await ctx.reply(f"📢 به {fa(sent)} گروه فرستاده شد ({fa(failed)} ناموفق).")


@command("admin_backup", ["backup"], "پشتیبان‌گیری", **_OPTIONS)
async def backup(ctx: CommandContext) -> None:
    if not _is_admin(ctx):
        return
    target = Path("backups") / f"game-{time.strftime('%Y%m%d-%H%M%S')}.db"
    path = await ctx.services.ctx.db.backup(target)
    await ctx.services.admin.log_action(ctx.user.id, "backup", str(target))
    await ctx.reply(f"💾 نسخه پشتیبان ساخته شد:\n{path}")

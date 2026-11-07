"""Gold transfers between players."""

from __future__ import annotations

from ...shared.errors import GameError
from ...shared.text import fa, to_int
from .context import CommandContext
from .registry import command


@command(
    "transfer", ["انتقال", "هدیه", "بده", "transfer"], "ارسال سکه: روی پیام کسی ریپلای کن و بنویس «انتقال 500»",
    category="💰 اقتصاد", takes_args=True, private=False,
)
async def transfer(ctx: CommandContext) -> None:
    target = await ctx.replied_player()
    amount = to_int(ctx.args[0]) if ctx.args else None
    if target is None or amount is None:
        raise GameError("روی پیام گیرنده ریپلای کن و بنویس: انتقال 500")
    left = await ctx.services.economy.transfer(ctx.me, target, amount)
    await ctx.reply(
        f"💸 {ctx.me.name} مبلغ {fa(amount)} سکه برای {target.name} فرستاد.\n"
        f"سهمیه امروز: {fa(left)} سکه باقی است."
    )


@command("wallet", ["کیف پول", "موجودی من", "سکه", "wallet"], "نمایش سکه و کریستال", category="💰 اقتصاد", points=0)
async def wallet(ctx: CommandContext) -> None:
    me = await ctx.services.players.require(ctx.user.id)
    await ctx.reply(f"💰 {me.name}\n🪙 سکه: {fa(me.gold)}\n💎 کریستال: {fa(me.crystal)}")

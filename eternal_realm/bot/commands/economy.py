"""Gold transfers between players."""

from __future__ import annotations

from ...shared.errors import GameError
from ...shared.text import bold, fa, to_int
from .. import panel
from .context import CommandContext
from .registry import command


@command(
    "transfer", ["انتقال", "هدیه", "بده", "transfer"], "بخشش سکه به دوستان: روی پیامش ریپلای کنید و بنویسید «انتقال 500»",
    category="💰 اقتصاد", takes_args=True, private=False,
)
async def transfer(ctx: CommandContext) -> None:
    target = await ctx.replied_player()
    if target is None:
        raise GameError("برای بخشیدن هدیه، روی پیام دوستتان ریپلای کنید و «انتقال» بنویسید.")
    amount = to_int(ctx.args[0]) if ctx.args else None
    if amount is not None:  # «انتقال 500»: open the amount page with gold already chosen
        await panel.send(ctx.message, ctx.services, ctx.me, "xamt", f"{target.id}.coin", str(amount), reply=True)
    else:
        await panel.send(ctx.message, ctx.services, ctx.me, "xfer", str(target.id), reply=True)


@command("wallet", ["کیف پول", "موجودی من", "سکه", "wallet"], "نمایش سکه و کریستال", category="💰 اقتصاد", points=0)
async def wallet(ctx: CommandContext) -> None:
    me = await ctx.services.players.require(ctx.user.id)
    await ctx.reply(
        f"💰 {bold('خزانه‌ی شما')}\n\nفرمانده {ctx.who(me)}\n\n🪙 سکه: {bold(fa(me.gold))}\n💎 کریستال: {bold(fa(me.crystal))}"
    )

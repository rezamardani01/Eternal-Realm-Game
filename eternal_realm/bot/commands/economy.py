"""Gold transfers between players."""

from __future__ import annotations

from ...shared.errors import GameError
from ...shared.text import bold, fa, to_int
from .context import CommandContext
from .registry import command


@command(
    "transfer", ["انتقال", "هدیه", "بده", "transfer"], "بخشش سکه به دوستان: روی پیامش ریپلای کنید و بنویسید «انتقال 500»",
    category="💰 اقتصاد", takes_args=True, private=False,
)
async def transfer(ctx: CommandContext) -> None:
    target = await ctx.replied_player()
    amount = to_int(ctx.args[0]) if ctx.args else None
    if target is None or amount is None:
        raise GameError("برای بخشش سکه، روی پیام دوستتان ریپلای کنید و بنویسید: «انتقال 500».")
    left = await ctx.services.economy.transfer(ctx.me, target, amount)
    await ctx.reply(
        f"💸 {bold('دست‌ودل‌بازی از فرمانده')} {ctx.who(ctx.me)}\n\n"
        f"مبلغ {bold(fa(amount))} سکه به {ctx.who(target)} بخشیده شد.\n\n"
        f"🏦 امروز می‌توانید {fa(left)} سکه‌ی دیگر ببخشید."
    )


@command("wallet", ["کیف پول", "موجودی من", "سکه", "wallet"], "نمایش سکه و کریستال", category="💰 اقتصاد", points=0)
async def wallet(ctx: CommandContext) -> None:
    me = await ctx.services.players.require(ctx.user.id)
    await ctx.reply(
        f"💰 {bold('خزانه‌ی شما')}\n\nفرمانده {ctx.who(me)}\n\n🪙 سکه: {bold(fa(me.gold))}\n💎 کریستال: {bold(fa(me.crystal))}"
    )

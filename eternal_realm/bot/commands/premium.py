"""The premium shop: opens in the private chat, where payments are made."""

from __future__ import annotations

from .. import keyboards, pages
from .context import CommandContext
from .registry import command


@command(
    "premium", ["فروشگاه ویژه", "بسته‌ها", "premium"], "فروشگاه ویژه: بسته‌های سکه، کریستال و صندوقچه",
    category="💎 فروشگاه ویژه", points=0,
)
async def premium(ctx: CommandContext) -> None:
    if ctx.is_group:
        username = ctx.services.bot_username
        await ctx.reply(
            "💎 خزانه‌ی ویژه فقط در پیام خصوصی ربات باز می‌شود؛ آنجا خرید امن است و با کیف پول بله پرداخت می‌کنید. روی دکمه‌ی زیر بزنید!",
            buttons=[keyboards.start_button(username)] if username else None,
        )
        return
    text, buttons = await pages.PAGES["premium"](ctx.services, ctx.me)
    await ctx.reply(text, buttons)

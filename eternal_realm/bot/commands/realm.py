"""The word «فرمانروایی»: in a group it shows a whole city (yours, or the hero you reply to)."""

from __future__ import annotations

from ...shared.errors import GameError
from .. import city_panel, keyboards, panel
from .context import CommandContext
from .registry import command


@command(
    "city_card", ["فرمانروایی", "شهر من", "شهر"],
    "فرمانروایی: مشخصات کامل شهر شما (یا شهر کسی که روی پیامش ریپلای کنید)؛ مردم، رضایت، آذوقه، منابع و سربازان",
    category="🏰 فرمانروایی", points=0, toggleable=True,
)
async def city_card(ctx: CommandContext) -> None:
    if not ctx.is_group and ctx.message.reply_to_message is None:
        await panel.send(ctx.message, ctx.services, ctx.me, "city", reply=True)  # in private the word opens the menu
        return
    target = await ctx.replied_player() or ctx.me
    city = await ctx.services.city.mine(target, visit=target.id == ctx.me.id)
    if city is None:
        if target.id == ctx.me.id:
            raise GameError("شما هنوز شهری ندارید. در پیام خصوصی ربات «فرمانروایی» را بزنید و شهرتان را بنا کنید.")
        raise GameError(f"{target.name} هنوز شهری در فرمانروایی ندارد.")
    buttons = None
    if target.id == ctx.me.id and ctx.services.bot_username:
        buttons = [keyboards.open_panel_button(ctx.services.bot_username)]
    await ctx.reply(city_panel.city_card_text(city, ctx.services.ctx.now()), buttons)

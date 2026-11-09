"""Buying a treasury pack as a gift for another hero: reply to their message and write «گیفت»."""

from __future__ import annotations

from ...shared.errors import GameError
from .. import panel
from .context import CommandContext
from .registry import command


@command(
    "gift_treasury", ["گیفت", "gift", "گیفت خزانه"],
    "گیفت: روی پیام یک نفر ریپلای کنید، از خزانه قلمرو چیزی برایش بخرید و او پیام هدیه می‌گیرد",
    category="💰 اقتصاد", private=False, toggleable=True, points=0,
)
async def gift_treasury(ctx: CommandContext) -> None:
    target = await ctx.replied_player()
    if target is None:
        raise GameError("روی پیام کسی که می‌خواهید برایش هدیه بخرید ریپلای کنید و «گیفت» بنویسید.")
    if target.id == ctx.me.id:
        raise GameError("گیفت برای دیگران است؛ برای خودتان از «خزانه قلمرو» در پیوی بخرید.")
    await panel.send(ctx.message, ctx.services, ctx.me, "gfs", str(target.id), reply=True)

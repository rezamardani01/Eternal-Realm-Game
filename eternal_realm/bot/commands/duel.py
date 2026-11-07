"""Challenging another player to a duel by replying to their message."""

from __future__ import annotations

from ...shared.errors import GameError
from .. import keyboards, views
from .context import CommandContext
from .registry import command


@command(
    "duel", ["مبارزه", "دوئل", "duel"], "دعوت به دوئل: روی پیام کسی ریپلای کن و بنویس «مبارزه»",
    category="⚔️ مبارزه", private=False, toggleable=True,
)
async def duel(ctx: CommandContext) -> None:
    target = await ctx.replied_player()
    if target is None:
        raise GameError("روی پیام کسی که می‌خواهی با او مبارزه کنی ریپلای کن و «مبارزه» بنویس.")
    service = ctx.services.duels
    duel_ = await service.challenge(ctx.chat_id, ctx.me, target)
    seconds = ctx.services.ctx.balance.duel_invite_seconds
    sent = await ctx.reply(views.duel_invite(ctx.me, target, seconds), keyboards.duel_invite(duel_.id))
    await service.attach_message(duel_.id, sent.message_id)

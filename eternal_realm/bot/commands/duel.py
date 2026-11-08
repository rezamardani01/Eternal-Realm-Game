"""Challenging another player to a duel by replying to their message."""

from __future__ import annotations

from ...shared.errors import GameError
from .. import keyboards, panel, views
from .context import CommandContext
from .registry import command


@command(
    "bet_duel", ["مبارزه شرطی", "دوئل شرطی", "شرط بندی"], "دوئل شرطی: سر سکه، کریستال یا منابع شرط ببندید و منتظر یک حریف بمانید",
    category="⚔️ مبارزه", private=False, toggleable=True,
)
async def bet_duel(ctx: CommandContext) -> None:
    await panel.send(ctx.message, ctx.services, ctx.me, "bet", reply=True)


@command(
    "duel", ["مبارزه", "دوئل", "duel"], "دوئل با یک حریف: روی پیامش ریپلای کنید و بنویسید «مبارزه»",
    category="⚔️ مبارزه", private=False, toggleable=True,
)
async def duel(ctx: CommandContext) -> None:
    target = await ctx.replied_player()
    if target is None:
        raise GameError("فرمانده، حریفتان را نشان دهید! روی پیام کسی که می‌خواهید با او بجنگید ریپلای کنید و «مبارزه» بنویسید.")
    service = ctx.services.duels
    duel_ = await service.challenge(ctx.chat_id, ctx.me, target)
    seconds = ctx.services.ctx.balance.duel_invite_seconds
    sent = await ctx.reply(views.duel_invite(ctx.me, target, seconds), keyboards.duel_invite(duel_.id))
    await service.attach_message(duel_.id, sent.message_id)

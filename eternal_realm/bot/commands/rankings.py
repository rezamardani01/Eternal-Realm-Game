"""Leaderboard commands."""

from __future__ import annotations

from .. import views
from .context import CommandContext
from .registry import command


@command(
    "rank", ["رتبه", "رتبه گروه", "فعال‌ترین‌ها", "rank"], "فعال‌ترین بازیکنان همین گروه",
    category="🏆 رتبه‌بندی", private=False, points=0,
)
async def rank(ctx: CommandContext) -> None:
    board = await ctx.services.rankings.group_board(ctx.chat_id)
    await ctx.reply(views.ranking(board))


@command(
    "top_level", ["برترین‌ها", "رتبه سطح", "top"], "بالاترین سطح‌ها در کل بازی",
    category="🏆 رتبه‌بندی", points=0,
)
async def top_level(ctx: CommandContext) -> None:
    await ctx.reply(views.ranking(await ctx.services.rankings.global_board("level", ctx.me)))


@command(
    "top_rich", ["ثروتمندان", "رتبه ثروت", "rich"], "ثروتمندترین بازیکنان",
    category="🏆 رتبه‌بندی", points=0,
)
async def top_rich(ctx: CommandContext) -> None:
    await ctx.reply(views.ranking(await ctx.services.rankings.global_board("rich", ctx.me)))


@command(
    "top_wins", ["قهرمانان", "رتبه مبارزه", "champions"], "بیشترین پیروزی در دوئل",
    category="🏆 رتبه‌بندی", points=0,
)
async def top_wins(ctx: CommandContext) -> None:
    await ctx.reply(views.ranking(await ctx.services.rankings.global_board("wins", ctx.me)))

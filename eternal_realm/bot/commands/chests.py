"""Chests: list, show the odds, open."""

from __future__ import annotations

from ...game.data.chests import CHESTS
from ...game.data.items import Kind, find_item
from ...shared.errors import GameError
from .. import views
from .context import CommandContext
from .registry import command


def _chest_item(text: str):  # noqa: ANN202
    item = find_item(text)
    if item is None or item.kind is not Kind.CHEST or item.id not in CHESTS:
        raise GameError("چنین صندوقچه‌ای در قلمرو نیست. «صندوقچه» را بنویسید تا فهرست را ببینید.")
    return item


@command(
    "chests", ["صندوقچه", "صندوقچه‌ها", "chests"], "فهرست صندوقچه‌ها و قیمتشان",
    category="🎁 صندوقچه", points=0,
)
async def chests(ctx: CommandContext) -> None:
    view = await ctx.services.inventory.view(ctx.me.id)
    owned = {item.id: qty for item, qty in view.stacks}
    await ctx.reply(views.chest_list(owned))


@command(
    "chest_odds", ["شانس", "odds"], "شانس دقیق محتویات صندوقچه: شانس <نام صندوقچه>",
    category="🎁 صندوقچه", takes_args=True, points=0,
)
async def chest_odds(ctx: CommandContext) -> None:
    item = _chest_item(ctx.raw_args)
    await ctx.reply(views.chest_odds(item, ctx.services.chests.odds(CHESTS[item.id])))


@command(
    "open_chest", ["باز کردن", "بازکن", "open"], "باز کردن صندوقچه: باز کردن <نام صندوقچه>",
    category="🎁 صندوقچه", takes_args=True,
)
async def open_chest(ctx: CommandContext) -> None:
    item = _chest_item(ctx.raw_args)
    opened = await ctx.services.chests.open(ctx.me, item)
    await ctx.reply(views.chest_opened(ctx.me.name, opened))

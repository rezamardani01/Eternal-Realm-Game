"""Backpack, equipment and consumables."""

from __future__ import annotations

from ...game.data.items import find_item
from ...shared.errors import GameError
from ...shared.text import to_int
from .. import views
from .context import CommandContext
from .registry import command


def _gear_id(ctx: CommandContext) -> int:
    number = to_int(ctx.args[0].lstrip("#")) if ctx.args else None
    if number is None:
        raise GameError("شماره‌ی تجهیزات را بنویسید. مثال: «تجهیز 12» (شماره‌ها را در «کوله‌پشتی» ببینید).")
    return number


@command(
    "inventory", ["کوله‌پشتی", "کیف", "کوله", "inventory"], "فهرست آیتم‌ها و تجهیزات",
    category="🎒 کوله‌پشتی", points=0,
)
async def inventory(ctx: CommandContext) -> None:
    view = await ctx.services.inventory.view(ctx.me.id)
    await ctx.reply(views.inventory(ctx.me.name, view))


@command(
    "equipment", ["تجهیزات", "تجهیزات من", "equipment"], "تجهیزات پوشیده‌شده (با ریپلای: دیگران)",
    category="🎒 کوله‌پشتی", points=0,
)
async def equipment(ctx: CommandContext) -> None:
    target = await ctx.replied_player() or ctx.me
    view = await ctx.services.inventory.view(target.id)
    stats = await ctx.services.characters.stats(target)
    await ctx.reply(views.equipment(target.name, view, stats))


@command(
    "equip", ["تجهیز", "بپوش", "equip"], "پوشیدن تجهیزات: تجهیز <شماره>",
    category="🎒 کوله‌پشتی", takes_args=True, points=0,
)
async def equip(ctx: CommandContext) -> None:
    piece, replaced = await ctx.services.inventory.equip(ctx.me, _gear_id(ctx))
    extra = f"\n↩️ {replaced.label} را کنار گذاشتید." if replaced else ""
    await ctx.reply(f"🛡️ {piece.label} را بر تن کردید و آماده‌تر از همیشه‌اید! {piece.stats.short()}{extra}")


@command(
    "unequip", ["درآوردن", "درآر", "unequip"], "درآوردن تجهیزات: درآوردن <شماره>",
    category="🎒 کوله‌پشتی", takes_args=True, points=0,
)
async def unequip(ctx: CommandContext) -> None:
    piece = await ctx.services.inventory.unequip(ctx.me, _gear_id(ctx))
    await ctx.reply(f"↩️ {piece.label} را از تن درآوردید و در کوله‌پشتی گذاشتید.")


@command(
    "use", ["مصرف", "بخور", "use"], "مصرف معجون: مصرف <نام>",
    category="🎒 کوله‌پشتی", takes_args=True,
)
async def use(ctx: CommandContext) -> None:
    item = find_item(ctx.raw_args)
    if item is None:
        raise GameError("چنین معجونی پیدا نشد. اسمش را درست بنویسید؛ مثال: «مصرف معجون انرژی».")
    await ctx.reply(await ctx.services.inventory.use(ctx.me, item))

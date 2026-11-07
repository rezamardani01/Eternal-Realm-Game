"""NPC shop commands: list, buy, sell and upgrade."""

from __future__ import annotations

from ...game.data.items import find_item
from ...shared.errors import GameError
from ...shared.text import fa, to_int
from .. import keyboards, views
from .context import CommandContext
from .registry import command


def _split_qty(args: list[str]) -> tuple[str, int]:
    """``['شمشیر', 'چوبی', '3']`` -> ``('شمشیر چوبی', 3)``."""
    if len(args) > 1 and (qty := to_int(args[-1])) is not None:
        return " ".join(args[:-1]), qty
    return " ".join(args), 1


def _item(text: str):  # noqa: ANN202
    item = find_item(text)
    if item is None:
        raise GameError("چنین آیتمی پیدا نشد. اسم دقیق آیتم را بنویس.")
    return item


def _gear_ref(text: str) -> int | None:
    return to_int(text.lstrip("#"))


@command("shop", ["فروشگاه", "بازارچه", "shop"], "فهرست کالاهای فروشگاه", category="🛒 فروشگاه", points=0)
async def shop(ctx: CommandContext) -> None:
    await ctx.reply(views.shop_listing())


@command(
    "buy", ["خرید", "buy"], "خرید از فروشگاه: خرید <نام> [تعداد]", category="🛒 فروشگاه", takes_args=True,
    toggleable=True,
)
async def buy(ctx: CommandContext) -> None:
    name, qty = _split_qty(ctx.args)
    item = _item(name)
    paid = await ctx.services.shop.buy(ctx.me, item, qty)
    await ctx.reply(f"✅ {item.label} ×{fa(qty)} خریدی؛ {fa(paid)} 🪙 پرداخت شد.")


@command(
    "sell", ["فروش", "sell"], "فروش به فروشگاه: فروش <نام> [تعداد] یا فروش #شماره تجهیزات",
    category="🛒 فروشگاه", takes_args=True, toggleable=True,
)
async def sell(ctx: CommandContext) -> None:
    if not ctx.args:
        raise GameError("چه چیزی را بفروشم؟ مثال: فروش ماهی کوچک 5  یا  فروش #12")
    if ctx.args[0].startswith("#") and (gear_id := _gear_ref(ctx.args[0])) is not None:
        piece, total = await ctx.services.shop.sell_gear(ctx.me, gear_id)
        await ctx.reply(f"💰 {piece.label} را فروختی و {fa(total)} 🪙 گرفتی.")
        return
    name, qty = _split_qty(ctx.args)
    item = _item(name)
    total = await ctx.services.shop.sell_stack(ctx.me, item, qty)
    await ctx.reply(f"💰 {item.label} ×{fa(qty)} را فروختی و {fa(total)} 🪙 گرفتی.")


@command(
    "upgrade", ["ارتقا", "ارتقاء", "upgrade"], "ارتقای تجهیزات: ارتقا <شماره>",
    category="🛒 فروشگاه", takes_args=True,
)
async def upgrade(ctx: CommandContext) -> None:
    gear_id = _gear_ref(ctx.args[0]) if ctx.args else None
    if gear_id is None:
        raise GameError("شماره تجهیزات را بنویس. مثال: ارتقا 12")
    piece, quote = await ctx.services.shop.quote(ctx.me, gear_id)
    await ctx.reply(
        views.upgrade_quote(piece, quote),
        keyboards.upgrade_confirm(piece.id, quote.next_level),
    )

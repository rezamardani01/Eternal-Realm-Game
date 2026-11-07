"""NPC shop commands: list, buy, sell and upgrade."""

from __future__ import annotations

from ...game.data.items import Kind, find_item
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
        raise GameError("چنین کالایی در قلمرو پیدا نشد. اسمش را دقیق‌تر بنویسید، یا «فروشگاه» را بزنید تا فهرست را ببینید.")
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
    if item.kind is Kind.CHEST:
        currency, total = await ctx.services.chests.buy(ctx.me, item.id, qty)
        icon = "🪙" if currency == "gold" else "💎"
        await ctx.reply(f"🛍️ انتخابی شایسته، فرمانده! {item.label} ×{fa(qty)} اکنون در اختیار شماست ({fa(total)} {icon} پرداخت شد).\n🗝️ برای گشودنش بنویسید: «باز کردن {item.name}»")
        return
    paid = await ctx.services.shop.buy(ctx.me, item, qty)
    await ctx.reply(f"🛍️ به‌به! انتخابی شایسته، فرمانده. {item.label} ×{fa(qty)} اکنون در اختیار شماست ({fa(paid)} 🪙 پرداخت شد).\nباشد که در نبردهای آینده یار و یاورتان باشد.")


@command(
    "sell", ["فروش", "sell"], "فروش به فروشگاه: فروش <نام> [تعداد] یا فروش #شماره تجهیزات",
    category="🛒 فروشگاه", takes_args=True, toggleable=True,
)
async def sell(ctx: CommandContext) -> None:
    if not ctx.args:
        raise GameError("چه چیزی را بفروشید، فرمانده؟ مثال: «فروش ماهی کوچک 5» یا برای سلاح و زره «فروش #12».")
    if ctx.args[0].startswith("#") and (gear_id := _gear_ref(ctx.args[0])) is not None:
        piece, total = await ctx.services.shop.sell_gear(ctx.me, gear_id)
        await ctx.reply(f"💰 معامله انجام شد! {piece.label} را فروختید و {fa(total)} 🪙 به کیسه‌تان ریخت.")
        return
    name, qty = _split_qty(ctx.args)
    item = _item(name)
    total = await ctx.services.shop.sell_stack(ctx.me, item, qty)
    await ctx.reply(f"💰 معامله انجام شد! {item.label} ×{fa(qty)} را فروختید و {fa(total)} 🪙 به کیسه‌تان ریخت.")


@command(
    "upgrade", ["ارتقا", "ارتقاء", "upgrade"], "ارتقای تجهیزات: ارتقا <شماره>",
    category="🛒 فروشگاه", takes_args=True,
)
async def upgrade(ctx: CommandContext) -> None:
    gear_id = _gear_ref(ctx.args[0]) if ctx.args else None
    if gear_id is None:
        raise GameError("آهنگر شماره‌ی تجهیزات را لازم دارد. مثال: «ارتقا 12» (شماره‌ها را در «کوله‌پشتی» ببینید).")
    piece, quote = await ctx.services.shop.quote(ctx.me, gear_id)
    await ctx.reply(
        views.upgrade_quote(piece, quote),
        keyboards.upgrade_confirm(piece.id, quote.next_level),
    )

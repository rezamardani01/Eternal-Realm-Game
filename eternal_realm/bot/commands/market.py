"""Player market commands: browse, list, buy and cancel."""

from __future__ import annotations

from ...game.data.items import find_item
from ...shared.errors import GameError
from ...shared.text import fa, to_int
from .. import views
from .context import CommandContext
from .registry import command


@command(
    "market", ["بازار", "market"], "آگهی‌های بازار (می‌توانید نام کالا را هم بنویسید: بازار شمشیر آهنی)",
    category="🏪 بازار", takes_args=True, points=0,
)
async def market(ctx: CommandContext) -> None:
    item = None
    if ctx.raw_args:
        item = find_item(ctx.raw_args)
        if item is None:
            raise GameError("چنین کالایی پیدا نشد. اسمش را دقیق‌تر بنویسید.")
    listings = await ctx.services.market.browse(item)
    await ctx.reply(views.market_listings(listings, item))


@command(
    "my_listings", ["آگهی‌های من", "آگهی من"], "آگهی‌های فعال خودتان", category="🏪 بازار", points=0,
)
async def my_listings(ctx: CommandContext) -> None:
    listings = await ctx.services.market.mine(ctx.me)
    await ctx.reply(views.market_listings(listings, None, title="🏷️ آگهی‌های من"))


@command(
    "list_item", ["عرضه", "بفروش", "list"],
    "آگهی فروش: عرضه #شماره‌تجهیزات قیمت  یا  عرضه <نام> <تعداد> <قیمت‌کل>",
    category="🏪 بازار", takes_args=True,
)
async def list_item(ctx: CommandContext) -> None:
    args = ctx.args
    usage = ("مثال: «عرضه #12 5000» یعنی سلاح شماره‌ی ۱۲ به بهای ۵۰۰۰ سکه؛ "
             "یا «عرضه سنگ آهن 10 900» یعنی ۱۰ سنگ آهن روی هم ۹۰۰ سکه.")
    if len(args) < 2 or (price := to_int(args[-1])) is None:
        raise GameError(usage)
    service = ctx.services.market
    if args[0].startswith("#"):
        gear_id = to_int(args[0].lstrip("#"))
        if gear_id is None:
            raise GameError(usage)
        listing = await service.list_gear(ctx.me, gear_id, price)
    else:
        if len(args) < 3 or (qty := to_int(args[-2])) is None:
            raise GameError(usage)
        item = find_item(" ".join(args[:-2]))
        if item is None:
            raise GameError("چنین کالایی پیدا نشد. اسمش را دقیق‌تر بنویسید.")
        listing = await service.list_stack(ctx.me, item, qty, price)
    fee = service.fee_for(price)
    await ctx.reply(
        f"🏷️ آگهی شما بر تخته‌ی بازار نصب شد! 🔖{fa(listing.id)}: {listing.label} به بهای {fa(price)} 🪙\n"
        f"کارمزد بازار ({fa(fee)} سکه) هنگام فروش کسر می‌شود. هر وقت خواستید بنویسید «لغو {fa(listing.id)}»."
    )


@command("buy_listing", ["بخر", "خرید آگهی"], "خرید از بازار: بخر <شماره آگهی>", category="🏪 بازار", takes_args=True)
async def buy_listing(ctx: CommandContext) -> None:
    listing_id = to_int(ctx.args[0].lstrip("🔖#")) if ctx.args else None
    if listing_id is None:
        raise GameError("شماره‌ی آگهی را بنویسید. مثال: «بخر 12» (شماره‌ها را در «بازار» ببینید).")
    listing = await ctx.services.market.buy(ctx.me, listing_id)
    await ctx.reply(f"🛍️ معامله مبارک، فرمانده! {listing.label} اکنون از آنِ شماست ({fa(listing.price)} 🪙 پرداخت شد).")


@command("cancel_listing", ["لغو", "لغو آگهی"], "لغو آگهی خودتان: لغو <شماره آگهی>", category="🏪 بازار", takes_args=True)
async def cancel_listing(ctx: CommandContext) -> None:
    listing_id = to_int(ctx.args[0].lstrip("🔖#")) if ctx.args else None
    if listing_id is None:
        raise GameError("شماره‌ی آگهی را بنویسید. مثال: «لغو 12».")
    listing = await ctx.services.market.cancel(ctx.me, listing_id)
    await ctx.reply(f"↩️ آگهی 🔖{fa(listing.id)} را پس گرفتید و {listing.label} به کوله‌پشتی‌تان برگشت.")

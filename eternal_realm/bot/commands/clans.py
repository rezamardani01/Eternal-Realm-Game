"""Words for the clan system: open the clan panel, found a clan, invite someone."""

from __future__ import annotations

from baleropy import Button

from ...shared.errors import GameError
from ...shared.text import bold, fa
from .. import panel
from ..callbacks import ClanCb
from .context import CommandContext
from .registry import command


@command(
    "clan", ["خاندان", "کلن", "clan"], "پنل خاندان: اعضا، مقام‌ها و خزانه", category="🏯 خاندان", points=0,
)
async def clan(ctx: CommandContext) -> None:
    await panel.send(ctx.message, ctx.services, ctx.me, "clan", reply=True)


@command(
    "clan_create", ["ساخت خاندان", "بساز خاندان"], "ساخت خاندان: ساخت خاندان نام‌دلخواه", category="🏯 خاندان",
    takes_args=True, points=0,
)
async def clan_create(ctx: CommandContext) -> None:
    if not ctx.raw_args:
        raise GameError("نام خاندان را هم بنویسید، فرمانده! مثال: «ساخت خاندان شیرهای شمال»")
    view = await ctx.services.clans.create(ctx.me, ctx.raw_args)
    price = ctx.services.ctx.balance.clan_create_gold
    await ctx.reply(
        f"🏯 {bold('خاندان ' + view.name + ' ساخته شد!')}\n\n"
        f"{ctx.who(ctx.me)} نخستین رهبر این خاندان شد و {bold(fa(price))} سکه از خزانه‌اش رفت.\n\n"
        "حالا دوستانتان را دعوت کنید (روی پیامشان ریپلای کنید و «دعوت خاندان» بنویسید) و برای مدیریت، «خاندان» را بنویسید."
    )


@command(
    "clan_invite", ["دعوت خاندان", "دعوت به خاندان"], "دعوت یک نفر به خاندان: روی پیامش ریپلای کنید",
    category="🏯 خاندان", private=False, points=0,
)
async def clan_invite(ctx: CommandContext) -> None:
    mine = await ctx.services.clans.of(ctx.me.id)
    if mine is None:
        raise GameError("شما عضو خاندانی نیستید. اول یکی بسازید: «ساخت خاندان نام».")
    if mine.my_role not in ("leader", "deputy"):
        raise GameError("دعوت کردن کار رهبر و معاون است.")
    target = await ctx.replied_player()
    if target is None:
        raise GameError("روی پیام کسی که می‌خواهید دعوت کنید ریپلای کنید و «دعوت خاندان» بنویسید.")
    if await ctx.services.clans.of(target.id) is not None:
        raise GameError(f"{target.name} همین حالا عضو یک خاندان است.")
    await ctx.reply(
        f"📜 {bold('دعوت‌نامه‌ی خاندان')}\n\n"
        f"{target.mention} ، {ctx.me.mention} شما را به خاندان {bold(mine.name)} دعوت کرده است.\n\n"
        "می‌پذیرید؟ فقط خودتان می‌توانید دکمه را بزنید 👇",
        [[Button.inline("✅ پذیرفتن دعوت", ClanCb(action="join", id=mine.id, arg=target.platform_user_id), style="success")]],
    )

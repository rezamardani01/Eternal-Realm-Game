"""Words for the clan system: open the clan panel, found a clan, invite someone."""

from __future__ import annotations

from baleropy import Button

from ...shared.errors import GameError
from ...shared.text import bold, fa
from .. import keyboards, panel
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
    from ...game.services.clans import clean_clan_name

    name = clean_clan_name(ctx.raw_args)
    price = ctx.services.ctx.balance.clan_create_gold
    me = await ctx.services.players.require(ctx.user.id)
    if me.gold < price:
        raise GameError(
            f"ساختن خاندان {fa(price)} سکه می‌خواهد. شما {fa(me.gold)} سکه دارید؛ {fa(price - me.gold)} سکه کم دارید."
        )
    await ctx.reply(
        f"🏯 {bold('تأیید ساخت خاندان')}\n\n"
        f"نام خاندان: {bold(name)}\n\n"
        f"هزینه: {bold(fa(price))} سکه\n\n"
        f"کیسه‌ی شما: {fa(me.gold)} ← {fa(me.gold - price)} سکه\n\n"
        "ساخته شود؟",
        [[
            keyboards.panel_button("✅ بله، بساز", "clancreate", me.platform_user_id, name),
            keyboards.panel_button("❌ نه", "clan", me.platform_user_id),
        ]],
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
        f"🎓 حداقل سطح عضویت: {fa(mine.min_level)}\n"
        f"⚖️ جریمه‌ی خیانت (خروج): {f'{fa(mine.exit_fine)} سکه' if mine.exit_fine else 'ندارد'}\n\n"
        "می‌پذیرید؟ فقط خودتان می‌توانید دکمه را بزنید 👇",
        [[Button.inline("✅ پذیرفتن دعوت", ClanCb(action="join", id=mine.id, arg=target.platform_user_id), style="success")]],
    )


@command(
    "rename", ["تغییر نام", "rename"], "تغییر نام قهرمان با برگه: تغییر نام نام‌تازه", category="👤 قهرمان",
    takes_args=True, points=0,
)
async def rename(ctx: CommandContext) -> None:
    from ...shared.validators import clean_name

    if not ctx.raw_args:
        raise GameError("نام تازه را هم بنویسید. مثال: «تغییر نام شیر شمال»")
    name = clean_name(ctx.raw_args)
    view = await ctx.services.inventory.view(ctx.me.id)
    if not any(i.id == "rename_ticket" and q > 0 for i, q in view.stacks):
        raise GameError("برای تغییر نام «برگه‌ی تغییر نام» لازم است. از «خزانه قلمرو» (پیام خصوصی ربات) تهیه کنید.")
    await ctx.reply(
        f"🏷️ {bold('تأیید تغییر نام')}\n\n"
        f"نام فعلی: {ctx.me.name}\n\nنام تازه: {bold(name)}\n\n"
        "یک برگه‌ی تغییر نام مصرف می‌شود. مطمئنید؟",
        [[
            keyboards.panel_button("✅ بله، عوض کن", "svcnamedo", ctx.me.platform_user_id, name),
            keyboards.panel_button("❌ نه", "home", ctx.me.platform_user_id),
        ]],
    )

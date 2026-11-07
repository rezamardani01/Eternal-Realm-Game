"""Profile, help, start and the daily reward."""

from __future__ import annotations

from ...shared.text import bold, fa
from .. import keyboards, panel, views
from .context import CommandContext
from .registry import REGISTRY, command


@command(
    "profile", ["پروفایل", "شخصیت", "مشخصات", "profile"], "قهرمان شما (با ریپلای: قهرمان دیگران)",
    category="👤 شخصیت", points=0,
)
async def profile(ctx: CommandContext) -> None:
    target = await ctx.replied_player()
    if target is None or target.id == ctx.me.id:
        await panel.send(ctx.message, ctx.services, ctx.me, "profile", reply=True)
        return
    stats = await ctx.services.characters.stats(target)
    chars = ctx.services.characters
    await ctx.reply(views.profile_lines(target, stats, chars.xp_needed(target), chars.max_energy(target)))


@command(
    "my_panel", ["اطلاعات من", "کیف من", "پنل", "منو", "panel"], "باز کردن پنل شخصی شما",
    category="👤 شخصیت", points=0,
)
async def my_panel(ctx: CommandContext) -> None:
    if ctx.is_group:
        username = ctx.services.bot_username
        await ctx.reply(
            f"📲 {bold('پنل شخصی')} فقط در پیام خصوصی باز می‌شود.",
            buttons=[keyboards.open_panel_button(username)] if username else None,
        )
        return
    await panel.send(ctx.message, ctx.services, ctx.me, "home")


@command("help", ["راهنما", "دستورات", "help"], "فهرست دستورها", category="👤 شخصیت", needs_player=False, points=0)
async def help_(ctx: CommandContext) -> None:
    player = await ctx.services.players.find(ctx.user.id)
    if player is not None:
        await panel.send(ctx.message, ctx.services, player, "help", reply=True)
        return
    await ctx.reply(views.command_help(REGISTRY, ctx.is_group))


@command(
    "start", ["start"], "شروع بازی", needs_player=False, private=False, always_on=True, points=0,
    category="👤 شخصیت",
)
async def start_in_group(ctx: CommandContext) -> None:
    username = ctx.services.bot_username
    await ctx.reply(
        f"🎮 برای ساختن قهرمان، ربات را در {bold('پیام خصوصی')} استارت کنید.",
        buttons=[keyboards.start_button(username)] if username else None,
    )


@command("daily", ["جایزه", "روزانه", "جایزه روزانه", "daily"], "گنجینه‌ی روزانه", category="👤 شخصیت")
async def daily(ctx: CommandContext) -> None:
    reward = await ctx.services.players.claim_daily(ctx.me.id)
    streak = f"\n🔥 {fa(reward.streak)} روز پشت‌سرهم!" if reward.streak > 1 else ""
    await ctx.reply(
        f"🎁 {bold('گنجینه‌ی روزانه')}\nفرمانده {ctx.me.name} ، {bold(fa(reward.gold))} سکه گرفتید.{streak}"
    )

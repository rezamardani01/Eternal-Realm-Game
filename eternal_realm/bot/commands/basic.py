"""Profile, help and the daily reward."""

from __future__ import annotations

from ...shared.text import fa
from .. import keyboards, pages, views
from .context import CommandContext
from .registry import REGISTRY, command


@command(
    "profile", ["پروفایل", "شخصیت", "مشخصات", "profile"], "نمایش مشخصات شخصیت (با ریپلای: مشخصات دیگران)",
    category="شخصیت", points=0,
)
async def profile(ctx: CommandContext) -> None:
    target = await ctx.replied_player() or ctx.me
    await ctx.reply(await pages.profile_text(ctx.services, target))


@command("help", ["راهنما", "دستورات", "help"], "فهرست دستورها", category="شخصیت", needs_player=False, points=0)
async def help_(ctx: CommandContext) -> None:
    await ctx.reply(views.command_help(REGISTRY, ctx.is_group))


@command(
    "start", ["start"], "شروع بازی", needs_player=False, private=False, always_on=True, points=0,
    category="شخصیت",
)
async def start_in_group(ctx: CommandContext) -> None:
    username = ctx.services.bot_username
    await ctx.reply(
        "🎮 برای ساختن قهرمان، ربات را در پیام خصوصی استارت کنید. دکمه‌ی زیر راه را نشانتان می‌دهد!",
        buttons=[keyboards.start_button(username)] if username else None,
    )


@command("daily", ["جایزه", "روزانه", "جایزه روزانه", "daily"], "دریافت جایزه روزانه", category="شخصیت")
async def daily(ctx: CommandContext) -> None:
    reward = await ctx.services.players.claim_daily(ctx.me.id)
    streak = f"\n🔥 {fa(reward.streak)} روز پشت‌سرهم آمده‌اید؛ هر روز پاداشتان بزرگ‌تر می‌شود!" if reward.streak > 1 else ""
    await ctx.reply(f"🎁 درود بر شما فرمانده {ctx.me.name}!\nپادشاه گنجینه‌ی امروز را فرستاد: {fa(reward.gold)} سکه{streak}\nامروز به کجا حمله می‌کنید؟")

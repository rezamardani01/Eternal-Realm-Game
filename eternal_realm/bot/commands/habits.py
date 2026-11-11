"""Words for the habits: friends, the group's weekly goal and the ranked season."""

from __future__ import annotations

from ...shared.errors import GameError
from ...shared.text import bar, bold, fa
from .. import keyboards, panel
from .context import CommandContext
from .registry import command


@command(
    "friend_add", ["دوست", "افزودن دوست", "دوست شو"], "دوستی: روی پیام کسی ریپلای کنید و «دوست» بنویسید",
    category="👤 شخصیت", points=0,
)
async def friend_add(ctx: CommandContext) -> None:
    target = await ctx.replied_player()
    if target is None:
        raise GameError("برای دوست شدن، روی پیام آن قهرمان ریپلای کنید و «دوست» بنویسید.")
    asked = await ctx.services.social.request(ctx.me, target.id)
    mutual = any(f.player_id == asked.id for f in await ctx.services.social.friends(ctx.me))
    if mutual:
        await ctx.reply(f"🤝 {bold('دوست شدید!')}\n\n{ctx.who(ctx.me)} و {ctx.who(asked)} حالا دوست‌اند. هر روز می‌توانید برای هم انرژی بفرستید.")
    else:
        await ctx.reply(f"👥 درخواست دوستی برای {ctx.who(asked)} رفت؛ در پیوی ربات خبرش می‌کنند.")


@command("friends", ["دوستان", "دوست ها", "دوست‌ها"], "فهرست دوستان و هدیه‌ی انرژی", category="👤 شخصیت", points=0)
async def friends(ctx: CommandContext) -> None:
    if ctx.is_group:
        username = ctx.services.bot_username
        await ctx.reply(
            f"👥 {bold('فهرست دوستان')} در پیام خصوصی باز می‌شود.",
            buttons=[keyboards.open_panel_button(username)] if username else None,
        )
        return
    await panel.send(ctx.message, ctx.services, ctx.me, "friends")


@command(
    "group_goal", ["هدف گروه", "هدف هفتگی", "هدف هفته"], "هدف هفتگی گروه: با هم شکار کنید", category="🌍 فعالیت‌ها",
    private=False, points=0,
)
async def group_goal(ctx: CommandContext) -> None:
    goal = await ctx.services.social.goal(ctx.chat_id, ctx.me.id)
    if goal is None:
        await ctx.reply(
            f"🎯 {bold('هدف هفتگی گروه')}\n\nاین هفته هنوز شکاری در گروه انجام نشده. با «شکار» شروع کنید؛ "
            "وقتی گروه به تعداد هدف برسد، همه‌ی کسانی که دست‌کم ۳ شکار کرده‌اند جایزه می‌گیرند."
        )
        return
    await ctx.reply(goal_text(goal))


def goal_text(goal) -> str:  # noqa: ANN001 - Goal
    left = max(0, goal.target - goal.done)
    return (
        f"🎯 {bold('هدف هفتگی گروه')}\n\n"
        f"🏹 شکارهای گروه: {fa(goal.done)} از {fa(goal.target)}\n{bar(min(goal.done, goal.target), goal.target, 10)}\n"
        + (f"🔥 {fa(left)} شکار دیگر مانده!" if left else "✅ هدف این هفته کامل شد!")
        + f"\n🙋 سهم شما: {fa(goal.mine)} شکار (برای جایزه دست‌کم ۳)"
        + "\n\nجایزه: سکه، ۲ کریستال و صندوقچه برای هر کس که کمک کرده."
    )


@command("season", ["فصل", "فصل رتبه‌بندی", "رتبه فصل"], "فصل رتبه‌بندی چهار هفته‌ای", category="🌍 فعالیت‌ها", points=0)
async def season(ctx: CommandContext) -> None:
    await panel.send(ctx.message, ctx.services, ctx.me, "rseason", reply=True)

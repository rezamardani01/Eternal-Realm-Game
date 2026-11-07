"""One group command per activity, generated from ``game/data/activities.py``."""

from __future__ import annotations

from ...game.data.activities import ACTIVITIES, Activity
from ...shared.text import fa
from .. import views
from .context import CommandContext
from .registry import Handler, command


def _make_handler(activity: Activity) -> Handler:
    async def handler(ctx: CommandContext) -> None:
        result = await ctx.services.activities.perform(ctx.me.id, activity.id)
        await ctx.reply(views.activity_result(ctx.me.name, result))

    return handler


for _activity in ACTIVITIES.values():
    command(
        _activity.id,
        list(_activity.aliases),
        f"{_activity.title} ({_activity.energy} انرژی)",
        category="🌍 فعالیت‌ها",
        toggleable=True,
    )(_make_handler(_activity))


@command("rest", ["استراحت", "بخواب", "rest"], "بازیابی انرژی (هر ۳۰ دقیقه)", category="🌍 فعالیت‌ها", points=0)
async def rest(ctx: CommandContext) -> None:
    restored = await ctx.services.activities.rest(ctx.me.id)
    await ctx.reply(f"🔥 فرمانده {ctx.me.name} کنار آتش نشست، نان و آب خورد و {fa(restored)} انرژی تازه گرفت ⚡\nآماده‌اید که دوباره به میدان بروید؟")


@command(
    "hunt", ["شکار", "برو شکار", "hunt"], "شکار هیولا (۱۰ انرژی)", category="🌍 فعالیت‌ها", toggleable=True,
)
async def hunt(ctx: CommandContext) -> None:
    result = await ctx.services.hunting.hunt(ctx.me.id)
    await ctx.reply(views.hunt_result(ctx.me.name, result))

"""One group command per activity, generated from ``game/data/activities.py``."""

from __future__ import annotations

from ...game.data.activities import ACTIVITIES, Activity
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

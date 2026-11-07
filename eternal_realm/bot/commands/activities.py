"""One group command per activity, generated from ``game/data/activities.py``."""

from __future__ import annotations

from ...game.data.activities import ACTIVITIES, Activity
from ...shared.text import bold, fa
from .. import keyboards, views
from .context import CommandContext
from .registry import Handler, command


def _make_handler(activity: Activity) -> Handler:
    async def handler(ctx: CommandContext) -> None:
        result = await ctx.services.activities.perform(ctx.me.id, activity.id)
        rows = keyboards.result_rows(
            ctx.me.platform_user_id, gold=result.rolled.gold, xp=result.rolled.xp, crystal=result.rolled.crystal,
            items=result.items, energy=result.player.energy, again=activity.id,
        )
        await ctx.play(
            views.activity_frames(ctx.who(ctx.me), result.activity), views.activity_result(ctx.who(ctx.me), result), rows
        )

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
    await ctx.reply(
        f"🔥 {bold('استراحت کنار آتش')}\n\n"
        f"فرمانده {ctx.who(ctx.me)} نان و آب خورد و {bold(fa(restored))} انرژی تازه گرفت ⚡\n\n"
        "آماده‌اید دوباره به میدان بروید؟"
    )


@command(
    "hunt", ["شکار", "برو شکار", "hunt"], "شکار هیولا (۱۰ انرژی)", category="🌍 فعالیت‌ها", toggleable=True,
)
async def hunt(ctx: CommandContext) -> None:
    result = await ctx.services.hunting.hunt(ctx.me.id)
    rows = keyboards.result_rows(
        ctx.me.platform_user_id, gold=result.gold, xp=result.xp, items=result.items,
        energy=result.player.energy, again="hunt", hp=(result.hero_hp, result.hero_max_hp),
    )
    await ctx.play(views.hunt_frames(ctx.who(ctx.me), result), views.hunt_result(ctx.who(ctx.me), result), rows)

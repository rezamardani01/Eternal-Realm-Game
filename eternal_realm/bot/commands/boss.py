"""Summon (or show) the group's boss."""

from __future__ import annotations

from ...shared.text import bold
from .. import boss as boss_ui
from .. import views
from .context import CommandContext
from .registry import command


@command(
    "boss", ["باس", "احضار باس", "boss"], "احضار باس گروهی و زدنش با همه (از سطح ۳)",
    category="🐉 باس گروهی", private=False, toggleable=True,
)
async def boss(ctx: CommandContext) -> None:
    services = ctx.services
    view = await services.bosses.active(ctx.chat_id)
    if view is not None:  # a boss is alive: bring its message back down to the bottom of the chat
        await boss_ui.post(ctx.message, services, view)
        return
    view = await services.bosses.summon(ctx.me, ctx.chat_id)
    frames = [
        f"🌑 {bold('آسمان تاریک شد...')}\nفرمانده {ctx.me.name} آیین احضار را آغاز کرد.",
        f"⚡ {bold('زمین می‌لرزد!')}\nچیزی بزرگ از دل تاریکی می‌آید...",
    ]
    sent = await ctx.play(frames, views.boss_summoned(view, ctx.me.name), boss_ui.buttons_for(services, view))
    await services.bosses.attach_message(view.id, sent.message_id)

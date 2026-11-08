"""Summon (or show) the group's boss."""

from __future__ import annotations

from ...shared.text import bold
from .. import boss as boss_ui
from .context import CommandContext
from .registry import command


@command(
    "boss", ["احضار باس", "باس", "boss"], "احضار باس گروهی؛ همه می‌پیوندند و نبرد خودکار انجام می‌شود (از سطح ۳)",
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
        f"🌑 {bold('آسمان تاریک شد...')}\nفرمانده {ctx.who(ctx.me)} آیین احضار را آغاز کرد.",
        f"⚡ {bold('زمین می‌لرزد!')}\nچیزی بزرگ از دل تاریکی می‌آید...",
    ]
    sent = await ctx.play(frames, boss_ui.text_for(services, view), boss_ui.buttons_for(view))
    await services.bosses.attach_message(view.id, sent.message_id)

"""The group's happenings: see what is going on, or (admins) ask the realm for a surprise."""

from __future__ import annotations

from ...game.services.events import KINDS, EventAction
from ...shared.errors import GameError
from .. import events as events_ui
from .. import views
from .context import CommandContext
from .group_admin import _require_admin
from .registry import command


@command(
    "events", ["رویدادها", "رویداد", "events"], "دیدن رویدادهای در جریان گروه", category="🎲 رویدادها",
    private=False, toggleable=True, needs_player=False, points=0,
)
async def events(ctx: CommandContext) -> None:
    active = await ctx.services.events.active(ctx.chat_id)
    boss = await ctx.services.bosses.active(ctx.chat_id)
    text = views.events_overview(active, any(v.kind == "double_xp" for v in active))
    if boss is not None:
        text += "\n\n🐉 یک باس در این گروه زنده است؛ بنویسید «باس»."
    await ctx.reply(text)


@command(
    "event", ["/event"], "(مدیر گروه) درخواست یک رویداد تازه: /event [mystery_chest|merchant|double_xp|hidden_boss]",
    category="⚙️ مدیریت گروه", needs_player=False, private=False, always_on=True, takes_args=True, points=0,
)
async def event(ctx: CommandContext) -> None:
    await _require_admin(ctx)
    kind = ctx.args[0] if ctx.args else None
    if kind is not None and kind not in KINDS:
        raise GameError("نوع رویداد درست نیست. این‌ها را می‌توانید بنویسید: " + "، ".join(KINDS))
    view = await ctx.services.events.spawn(ctx.chat_id, kind)
    if view is None:
        raise GameError("الان در این گروه یک رویداد یا باس در جریان است؛ کمی صبر کنید تا تمام شود.")
    await events_ui.announce(ctx.bot, ctx.services, EventAction("spawned", view))

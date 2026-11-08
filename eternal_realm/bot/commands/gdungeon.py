"""«سیاه‌چال گروهی»: open the lobby in a group."""

from __future__ import annotations

from .. import group_dungeon as ui
from .context import CommandContext
from .registry import command


@command(
    "gdungeon", ["سیاه‌چال گروهی", "ورود به سیاه‌چال", "سیاهچال گروهی", "gdungeon"],
    "سیاه‌چال گروهی با ۳ تا ۵ نفر و نگهبان در آخر (از سطح ۵)", category="🕳️ سیاه‌چال", private=False, toggleable=True,
)
async def gdungeon(ctx: CommandContext) -> None:
    view = await ctx.services.gdungeon.open(ctx.chat_id, ctx.me)
    sent = await ctx.reply(ui.lobby_text(view), ui.lobby_buttons(view.id))
    await ctx.services.gdungeon.attach_message(view.id, sent.message_id)

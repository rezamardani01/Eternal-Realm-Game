"""Opening a team battle lobby in a group."""

from __future__ import annotations

from .. import team_battle
from .context import CommandContext
from .registry import command


@command(
    "team_battle", ["مبارزه تیمی", "نبرد تیمی", "جنگ تیمی"],
    "مبارزه‌ی تیمی: دو تیم روبه‌روی هم؛ هر کس جایگاهی می‌گیرد و سازنده نبرد را شروع می‌کند",
    category="⚔️ مبارزه", private=False, toggleable=True,
)
async def team_battle_lobby(ctx: CommandContext) -> None:
    lobby = await ctx.services.teams.create(ctx.chat_id, ctx.me)
    left = lobby.expires_at - ctx.services.ctx.now()
    sent = await ctx.say(team_battle.lobby_text(lobby, left), team_battle.lobby_buttons(lobby))
    await ctx.services.teams.attach_message(lobby.id, sent.message_id)

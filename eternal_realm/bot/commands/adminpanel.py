"""«پنل مدیریت»: the owner or an admin opens the glass-button management panel."""

from __future__ import annotations

from ...shared.errors import GameError
from .. import panel
from .context import CommandContext
from .registry import command


@command(
    "manage_panel", ["پنل مدیریت", "پنل ادمین", "مدیریت ربات"], "(مدیر) پنل مدیریت شیشه‌ای", needs_player=False,
    private=True, group=True, always_on=True, points=0, category="🛠️ مدیریت",
)
async def manage_panel(ctx: CommandContext) -> None:
    if not ctx.services.ctx.settings.is_admin(ctx.user.id):
        return  # silent for everybody else, like the other admin tools
    me = await ctx.services.players.find(ctx.user.id)
    if me is None:
        raise GameError("اول قهرمان خودتان را بسازید: ربات را در پیوی استارت کنید.")
    await panel.send(ctx.message, ctx.services, me, "adm", reply=True)

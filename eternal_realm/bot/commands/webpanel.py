"""«پنل وب»: the owner or an admin gets a one-time login link for the web admin panel."""

from __future__ import annotations

from ...shared.errors import GameError
from ...shared.text import bold
from ...web.auth import LINK_TTL
from .context import CommandContext
from .registry import command


@command(
    "web_panel", ["پنل وب", "webpanel", "web"], "لینک یک‌بارمصرف ورود به پنل مدیریت وب", needs_player=False, group=False,
    always_on=True, points=0, category="🛠️ مدیریت",
)
async def web_panel(ctx: CommandContext) -> None:
    settings = ctx.services.ctx.settings
    if not settings.is_admin(ctx.user.id):
        return  # silent for everybody else, like the other admin tools
    if not settings.web_enabled or not settings.web_url:
        raise GameError(
            "پنل وب هنوز تنظیم نشده. در config.toml بخش [web] را پر کنید (enabled = true و public_url) و ربات را ری‌استارت کنید."
        )
    token = ctx.services.web_auth.issue_link_token(ctx.user.id)
    await ctx.reply(
        f"🖥️ {bold('ورود به پنل مدیریت وب')}\n\n"
        f"{settings.web_url}/login?token={token}\n\n"
        f"این لینک فقط {LINK_TTL // 60} دقیقه و فقط یک بار کار می‌کند. آن را برای کسی نفرستید.\n"
        "اگر منقضی شد، دوباره «پنل وب» را بفرستید."
    )

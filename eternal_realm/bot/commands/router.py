"""The single entry point for every text message: resolve -> guard -> run."""

from __future__ import annotations

from baleropy import Bot, F, Router
from baleropy.types import Message

from ...shared.errors import GameError
from .. import keyboards
from ..services import Services
from .context import CommandContext
from .registry import REGISTRY

router = Router(name="commands")


def _is_private(message: Message) -> bool:
    return str(getattr(message.chat.type, "value", message.chat.type)) == "private"


@router.message(F.text)
async def on_text(message: Message, bot: Bot, services: Services) -> None:
    user = message.from_user
    if user is None or user.is_bot or not message.text:
        return
    match = REGISTRY.resolve(message.text)
    if match is None:
        return
    cmd = match.command
    private = _is_private(message)

    if private and not cmd.private:
        raise GameError("این فرمان مال میدان‌های گروهی است! ربات را به یک گروه ببرید و آنجا امتحانش کنید.")
    if not private and not cmd.group:
        return
    if user.id != services.ctx.settings.owner_id and not services.throttle.allow_user(user.id):
        return

    if not private:
        if user.id != services.ctx.settings.owner_id and not services.throttle.allow_group(message.chat.id):
            return
        group = await services.groups.touch(message.chat.id, message.chat.title)
        if not cmd.always_on:
            if not group.enabled:
                return
            if cmd.name in group.disabled_commands:
                raise GameError("فرمانده، مدیر این گروه این فعالیت را فعلاً بسته است. شاید بعداً دوباره باز شود!")

    player = None
    if cmd.needs_player:
        player = await services.players.find(user.id, user.username)
        if player is None:
            await message.reply(
                "🎮 ای ماجراجوی ناشناس! هنوز قهرمانی نساخته‌اید. به پیام خصوصی ربات بروید، شروع را بزنید و قهرمان خود را بسازید؛ بعد برگردید و ماجراجویی کنید!",
                buttons=[keyboards.start_button(services.bot_username)] if services.bot_username else None,
            )
            return
        if player.banned:
            raise GameError("⛔ نگهبانان قلمرو درهای شهر را به روی شما بسته‌اند. اگر فکر می‌کنید اشتباهی شده، با مدیر ربات صحبت کنید.")

    ctx = CommandContext(message, bot, services, cmd, match.args, match.raw_args, player)
    await cmd.handler(ctx)
    if not private and player is not None and cmd.points:
        await services.groups.add_points(message.chat.id, player.id, cmd.points)

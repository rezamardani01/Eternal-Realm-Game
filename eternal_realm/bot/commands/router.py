"""The single entry point for every text message: resolve -> guard -> run."""

from __future__ import annotations

import time

from baleropy import Bot, F, Router
from baleropy.types import Message

from ...shared.errors import GameError
from .. import keyboards
from ..services import Services
from .context import CommandContext
from .registry import REGISTRY

router = Router(name="commands")

#: seconds before the same stranger is told again, in a group, that they have no hero yet (the group is not a notice board)
STRANGER_GAP = 180
_told: dict[int, float] = {}


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
        return  # words that belong to the private chat get no answer at all in a group
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
            now = time.monotonic()
            if not private and now - _told.get(user.id, -STRANGER_GAP) < STRANGER_GAP:
                return  # told a moment ago: stay quiet instead of filling the group
            if len(_told) > 5000:
                _told.clear()
            _told[user.id] = now
            await message.reply(
                "🎮 هنوز قهرمانی نساخته‌اید!\nدکمه‌ی زیر را بزنید، قهرمانتان را بسازید و برگردید 👇",
                buttons=[keyboards.start_button(services.bot_username)] if services.bot_username else None,
            )
            return
        if player.banned:
            raise GameError("⛔ نگهبانان قلمرو درهای شهر را به روی شما بسته‌اند. اگر فکر می‌کنید اشتباهی شده، با مدیر ربات صحبت کنید.")

    ctx = CommandContext(message, bot, services, cmd, match.args, match.raw_args, player)
    from ..academy_panel import after as academy_after

    try:
        await cmd.handler(ctx)
    except GameError:
        if player is not None:  # a refused try (full energy, a wait) still teaches the lessons that are about knowing it
            await academy_after(bot, services, player, player.platform_user_id, command=cmd.name, attempted=True)
        raise
    if player is not None:  # the academy notices lessons learned by words (sent here or in a group); quiet otherwise
        await academy_after(bot, services, player, player.platform_user_id, command=cmd.name)
    if not private and player is not None and cmd.points:
        await services.groups.add_points(message.chat.id, player.id, cmd.points)

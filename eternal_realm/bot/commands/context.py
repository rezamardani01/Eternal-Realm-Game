"""What a command handler receives."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from baleropy import Bot
from baleropy.exceptions import BaleAPIError
from baleropy.types import Message, User

from ...game.models import Player
from ...shared.errors import GameError
from ...shared.text import headline
from ..keyboards import Rows
from ..services import Services
from .registry import Command


@dataclass
class CommandContext:
    message: Message
    bot: Bot
    services: Services
    command: Command
    args: list[str]
    raw_args: str
    player: Player | None

    @property
    def user(self) -> User:
        assert self.message.from_user is not None
        return self.message.from_user

    @property
    def chat_id(self) -> int:
        return self.message.chat.id

    @property
    def is_group(self) -> bool:
        return str(getattr(self.message.chat.type, "value", self.message.chat.type)) != "private"

    @property
    def me(self) -> Player:
        """The caller's character (commands with ``needs_player`` always have one)."""
        assert self.player is not None
        return self.player

    async def reply(self, text: str, buttons: Rows | None = None) -> Message:
        text = headline(text)
        if buttons:
            return await self.message.reply(text, buttons=buttons)
        return await self.message.reply(text)

    async def play(self, frames: list[str], final: str, buttons: Rows | None = None) -> None:
        """Send the first frame, edit the same message through the rest, finish with ``final``."""
        if not frames:
            await self.reply(final, buttons)
            return
        sent = await self.reply(frames[0])
        pause = self.services.ctx.pause
        for frame in frames[1:]:
            await pause()
            await _edit(sent, frame)
        await pause()
        await _edit(sent, final, buttons)

    async def say(self, text: str, buttons: Rows | None = None) -> Message:
        text = headline(text)
        """Send to the chat without quoting the command."""
        if buttons:
            return await self.message.answer(text, buttons=buttons)
        return await self.message.answer(text)

    async def replied_player(self) -> Player | None:
        """The character of whoever the command message replies to (``None`` without a reply)."""
        target_msg = self.message.reply_to_message
        if target_msg is None or target_msg.from_user is None:
            return None
        target = target_msg.from_user
        if target.is_bot:
            raise GameError("ربات‌ها اهل نبرد و معامله نیستند، فرمانده! روی پیام یک بازیکن واقعی ریپلای کنید.")
        found = await self.services.players.find(target.id, target.username)
        if found is None:
            raise GameError(f"{target.full_name or 'این کاربر'} هنوز قهرمانی نساخته و از قلمرو خبر ندارد! از او بخواهید ربات را استارت کند.")
        return found


async def _edit(message: Message, text: str, buttons: Rows | None = None) -> None:
    text = headline(text)
    with contextlib.suppress(BaleAPIError):  # e.g. the message was deleted meanwhile
        await message.edit_text(text, buttons=buttons) if buttons else await message.edit_text(text)

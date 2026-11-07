"""What a command handler receives."""

from __future__ import annotations

from dataclasses import dataclass

from baleropy import Bot
from baleropy.types import Message, User

from ...game.models import Player
from ...shared.errors import GameError
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
        if buttons:
            return await self.message.reply(text, buttons=buttons)
        return await self.message.reply(text)

    async def say(self, text: str, buttons: Rows | None = None) -> Message:
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
            raise GameError("روی ربات‌ها نمی‌شود این کار را کرد.")
        found = await self.services.players.find(target.id, target.username)
        if found is None:
            raise GameError(f"{target.full_name or 'این کاربر'} هنوز در بازی شخصیت نساخته است.")
        return found

"""Forced channel membership: which channels a player must have joined before playing.

The list lives in the database (``app_settings``) so the admin panel can change it without a restart.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from ...context import AppContext
from ...shared.errors import GameError

KEY = "membership"
MAX_CHANNELS = 5
CACHE_SECONDS = 600
_CHAT = re.compile(r"^(@[A-Za-z][A-Za-z0-9_]{2,}|-?\d{5,})$")
JOINED = {"creator", "administrator", "member", "restricted"}


@dataclass
class Channel:
    chat: str
    title: str = ""
    link: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"chat": self.chat, "title": self.title, "link": self.link}

    @property
    def url(self) -> str:
        if self.link:
            return self.link
        return f"https://ble.ir/{self.chat[1:]}" if self.chat.startswith("@") else ""


class MembershipService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._ok: dict[tuple[int, str], float] = {}

    # --- settings ------------------------------------------------------------------------------------
    async def settings(self) -> tuple[bool, list[Channel]]:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT value FROM app_settings WHERE key = ?", (KEY,))
        if row is None:
            return False, []
        data = json.loads(row["value"])
        return bool(data.get("enabled")), [Channel(**c) for c in data.get("channels", [])]

    async def save(self, enabled: bool, channels: list[dict[str, str]]) -> None:
        if len(channels) > MAX_CHANNELS:
            raise GameError(f"حداکثر {MAX_CHANNELS} کانال می‌شود تنظیم کرد.")
        clean: list[Channel] = []
        for c in channels:
            chat = str(c.get("chat", "")).strip()
            link = str(c.get("link", "")).strip()
            title = str(c.get("title", "")).strip()[:60]
            if not _CHAT.match(chat):
                raise GameError("شناسه‌ی کانال باید یوزرنیم (مثل @mychannel) یا شناسه‌ی عددی باشد.")
            if link and not (link.startswith("https://") and " " not in link):
                raise GameError("لینک دعوت باید با https:// شروع شود.")
            if any(x.chat == chat for x in clean):
                raise GameError("یک کانال دو بار نوشته شده است.")
            clean.append(Channel(chat, title, link))
        if enabled and not clean:
            raise GameError("برای فعال کردن عضویت اجباری، دست‌کم یک کانال بگذارید.")
        payload = json.dumps({"enabled": enabled, "channels": [c.as_dict() for c in clean]}, ensure_ascii=False)
        async with self.ctx.db.transaction() as tx:
            await tx.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value", (KEY, payload),
            )
        self._ok.clear()

    # --- checking --------------------------------------------------------------------------------------
    async def missing(self, bot, user_id: int) -> list[Channel]:  # noqa: ANN001
        """Channels the user has not joined. Problems talking to Bale never lock players out."""
        if self.ctx.settings.is_admin(user_id):
            return []
        enabled, channels = await self.settings()
        if not enabled or not channels:
            return []
        now = time.monotonic()
        out = []
        for channel in channels:
            if self._ok.get((user_id, channel.chat), 0) > now:
                continue
            try:
                member = await bot.get_chat_member(self._chat_id(channel.chat), user_id)
                status = getattr(member.status, "value", member.status)
            except Exception:
                continue  # the channel is unreachable (bot not an admin there?): fail open
            if status in JOINED:
                self._ok[(user_id, channel.chat)] = now + CACHE_SECONDS
            else:
                out.append(channel)
        return out

    @staticmethod
    def _chat_id(chat: str) -> str | int:
        return chat if chat.startswith("@") else int(chat)

    def forget(self, user_id: int) -> None:
        for key in [k for k in self._ok if k[0] == user_id]:
            del self._ok[key]

    async def probe(self, bot, chat: str) -> dict[str, str]:  # noqa: ANN001
        """For the admin panel: can the bot see this channel, and is it an admin there?"""
        if not _CHAT.match(chat):
            raise GameError("شناسه‌ی کانال درست نیست.")
        try:
            info = await bot.get_chat(self._chat_id(chat))
        except Exception as exc:
            raise GameError("ربات این کانال را پیدا نکرد. ربات را در کانال ادمین کنید و شناسه را دوباره بررسی کنید.") from exc
        title = str(getattr(info, "title", "") or "")
        try:
            me = await bot.me()
            member = await bot.get_chat_member(self._chat_id(chat), me.id)
            status = str(getattr(member.status, "value", member.status))
        except Exception:
            status = "unknown"
        return {"title": title, "bot_status": status}

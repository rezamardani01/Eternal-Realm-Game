"""Maintenance mode: while it is on (panel: «حالت تعمیر») only managers can use the bot."""

from __future__ import annotations

import time
from typing import Any

from baleropy.dispatcher import BaseMiddleware
from baleropy.types import CallbackQuery, Message

from ..shared.text import bold, headline
from .commands.registry import REGISTRY
from .services import Services

NOTICE_GAP = 60  # seconds between two notices to the same person
CACHE_SECONDS = 5

DEFAULT_TEXT = "ربات برای به‌روزرسانی و بهبود موقتاً در دسترس نیست. کمی بعد دوباره سر بزنید."


def notice(text: str) -> str:
    return headline(f"🚧 {bold('قلمرو در حال تعمیر است')}\n\n{text or DEFAULT_TEXT}")


class MaintenanceMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._noticed: dict[int, float] = {}
        self._cached: tuple[float, bool, str, int] | None = None

    async def _state(self, services: Services) -> tuple[bool, str]:
        now = time.monotonic()
        version = services.admin.maintenance_version
        if self._cached is None or now - self._cached[0] > CACHE_SECONDS or self._cached[3] != version:
            enabled, text = await services.admin.maintenance()
            self._cached = (now, enabled, text, version)
        return self._cached[1], self._cached[2]

    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        services: Services | None = data.get("services")
        user = getattr(event, "from_user", None)
        if services is None or user is None or user.is_bot or services.ctx.settings.is_admin(user.id):
            return await handler(event, data)
        enabled, text = await self._state(services)
        if not enabled:
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            await event.answer("🚧 ربات در حال تعمیر است؛ کمی بعد برگردید.", show_alert=True)
            return None
        if isinstance(event, Message):
            private = str(getattr(event.chat.type, "value", event.chat.type)) == "private"
            if not private and not (event.text and REGISTRY.resolve(event.text) is not None):
                return await handler(event, data)  # ordinary group chat is none of our business
            now = time.monotonic()
            last = self._noticed.get(user.id)
            if last is None or now - last >= NOTICE_GAP:
                self._noticed[user.id] = now
                await event.reply(notice(text))
            return None
        return await handler(event, data)

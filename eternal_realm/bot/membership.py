"""The gate: nobody plays until they have joined the required channels."""

from __future__ import annotations

import time
from typing import Any

from baleropy import Button, F, Router
from baleropy.dispatcher import BaseMiddleware
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery, Message

from ..game.services.membership import Channel
from ..shared.text import bold, headline
from .callbacks import PanelCb
from .commands.registry import REGISTRY
from .services import Services

router = Router(name="membership")
CHECK = "mem:check"
NOTICE_GAP = 60  # seconds between two notices to the same person in a group


def notice_text(missing: list[Channel]) -> str:
    names = "\n".join(f"📣 {c.title or c.chat}" for c in missing)
    return headline(
        f"🔒 {bold('عضویت در کانال لازم است')}\n\n"
        "برای بازی کردن اول باید در کانال زیر عضو شوید:\n\n"
        f"{names}\n\n"
        "بعد از عضو شدن، دکمه‌ی «عضو شدم» را بزنید 👇"
    )


def notice_buttons(missing: list[Channel]):  # noqa: ANN201
    rows = [[Button.url(f"📣 عضویت در {c.title or c.chat}", c.url)] for c in missing if c.url]
    rows.append([Button.inline("✅ عضو شدم", CHECK, style="success")])
    return rows


class MembershipMiddleware(BaseMiddleware):
    """Blocks private chat, panel buttons and game words in groups for people who have not joined."""

    def __init__(self) -> None:
        self._noticed: dict[int, float] = {}

    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        services: Services | None = data.get("services")
        bot = data.get("bot")
        user = getattr(event, "from_user", None)
        if services is None or bot is None or user is None or user.is_bot:
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            if event.data == CHECK:
                return await handler(event, data)
            gated = True
        elif isinstance(event, Message):
            private = str(getattr(event.chat.type, "value", event.chat.type)) == "private"
            text = event.text or ""
            gated = private or (bool(text) and REGISTRY.resolve(text) is not None)
        else:
            gated = False
        if not gated:
            return await handler(event, data)
        missing = await services.membership.missing(bot, user.id)
        if not missing:
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            await event.answer("🔒 اول باید در کانال عضو شوید. /start را بزنید.", show_alert=True)
            return None
        now = time.monotonic()
        if event.chat.id != user.id and now - self._noticed.get(user.id, 0) < NOTICE_GAP:
            return None  # do not flood a group with notices
        self._noticed[user.id] = now
        if len(self._noticed) > 5000:
            self._noticed = {u: t for u, t in self._noticed.items() if now - t < NOTICE_GAP}
        await event.reply(notice_text(missing), buttons=notice_buttons(missing))
        return None


@router.callback_query(F.data == CHECK)
async def on_check(query: CallbackQuery, services: Services, bot) -> None:  # noqa: ANN001
    services.membership.forget(query.from_user.id)
    missing = await services.membership.missing(bot, query.from_user.id)
    if missing:
        await query.answer("هنوز عضو نشده‌اید؛ اول در کانال عضو شوید و دوباره بزنید.", show_alert=True)
        return
    await query.answer("✅ عضویت تأیید شد!")
    if query.message is not None:
        try:
            await query.message.edit_text(
                headline(f"✅ {bold('عضویت تأیید شد')}\n\nخوش آمدید! حالا می‌توانید وارد قلمرو شوید."),
                buttons=[[Button.inline("🏰 ورود به قلمرو", PanelCb(s="home", o=query.from_user.id), style="success")]],
            )
        except BaleAPIError:
            pass

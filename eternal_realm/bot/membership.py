"""The gate: nobody plays until they have joined the required channels."""

from __future__ import annotations

import contextlib
import time
from typing import Any

from baleropy import Button, F, Router
from baleropy.dispatcher import BaseMiddleware
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery, Message

from ..game.services.membership import Channel
from ..shared.text import bold, headline
from .callbacks import PanelCb
from .services import Services

router = Router(name="membership")
CHECK = "mem:check"


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


def _is_private(chat: Any) -> bool:
    return str(getattr(chat.type, "value", chat.type)) == "private"


class MembershipMiddleware(BaseMiddleware):
    """Blocks the private chat with the bot (messages and buttons) for people who have not joined the channels."""

    def __init__(self) -> None:
        self._warned_at: float | None = None

    async def _warn_admins(self, bot: Any, services: Services) -> None:
        """When Bale refuses the membership check the owner is told why (at most once an hour)."""
        problems = services.membership.problems
        now = time.monotonic()
        if not problems or (self._warned_at is not None and now - self._warned_at < 3600):
            return
        self._warned_at = now
        lines = "\n".join(f"📣 {chat}" for chat in problems)
        text = headline(
            f"⚠️ {bold('عضویت اجباری کار نمی‌کند')}\n\n"
            "ربات نتوانست عضویت را در این کانال‌ها بررسی کند:\n"
            f"{lines}\n\n"
            "ربات را در هر کانال «ادمین» کنید و شناسه‌ی کانال را بررسی کنید؛ تا آن موقع بازیکنان وارد بازی نمی‌شوند.\n"
            "در «پنل مدیریت ← عضویت اجباری» وضعیت هر کانال را می‌بینید."
        )
        with contextlib.suppress(BaleAPIError):
            await bot.send_message(services.ctx.settings.owner_id, text)
    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        services: Services | None = data.get("services")
        bot = data.get("bot")
        user = getattr(event, "from_user", None)
        if services is None or bot is None or user is None or user.is_bot:
            return await handler(event, data)
        # the gate only guards the private chat with the bot; groups are never checked or nagged
        if isinstance(event, CallbackQuery):
            if event.data == CHECK:
                return await handler(event, data)
            chat = event.message.chat if event.message is not None else None
            gated = chat is not None and _is_private(chat)
        elif isinstance(event, Message):
            gated = _is_private(event.chat)
        else:
            gated = False
        if not gated:
            return await handler(event, data)
        missing = await services.membership.missing(bot, user.id)
        await self._warn_admins(bot, services)
        if not missing:
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            await event.answer("🔒 اول باید در کانال عضو شوید. /start را بزنید.", show_alert=True)
            return None
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

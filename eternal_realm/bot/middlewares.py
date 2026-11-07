"""Cross-cutting behaviour: friendly game errors and a safety net for crashes."""

from __future__ import annotations

import logging
from typing import Any

from baleropy.dispatcher import BaseMiddleware
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery, Message

from ..shared.errors import GameError
from ..shared.text import headline

log = logging.getLogger("eternal_realm.bot")

GENERIC_ERROR = "😵 اوه! طوفانی در قلمرو وزید و کار نیمه‌کاره ماند. نگران نباشید، چند لحظه دیگر دوباره امتحان کنید."


class ErrorMiddleware(BaseMiddleware):
    """Turns :class:`GameError` into a reply and logs everything unexpected."""

    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        try:
            return await handler(event, data)
        except GameError as error:
            await self._tell(event, error.message)
        except BaleAPIError:
            log.exception("Bale API error while handling an update")
        except Exception:
            log.exception("Unhandled error while handling an update")
            await self._tell(event, GENERIC_ERROR)
        return None

    @staticmethod
    async def _tell(event: Any, text: str) -> None:
        try:
            if isinstance(event, CallbackQuery):
                if len(text) <= 190:
                    await event.answer(text, show_alert=True)
                else:
                    await event.answer("⚠️ پیام را در گفتگو بخوانید 👇", show_alert=False)
                    if event.message is not None:
                        await event.message.answer(text)
            elif isinstance(event, Message):
                await event.reply(headline(text))
        except BaleAPIError:
            log.warning("could not deliver an error message", exc_info=True)

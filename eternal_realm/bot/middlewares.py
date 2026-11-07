"""Cross-cutting behaviour: friendly game errors and a safety net for crashes."""

from __future__ import annotations

import logging
from typing import Any

from baleropy.dispatcher import BaseMiddleware
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery, Message

from ..shared.errors import GameError

log = logging.getLogger("eternal_realm.bot")

GENERIC_ERROR = "😵 مشکلی پیش آمد، چند لحظه دیگر دوباره امتحان کن."


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
                await event.answer(text[:190], show_alert=True)
            elif isinstance(event, Message):
                await event.reply(text)
        except BaleAPIError:
            log.warning("could not deliver an error message", exc_info=True)

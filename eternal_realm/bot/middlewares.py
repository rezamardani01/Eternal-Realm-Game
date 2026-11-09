"""Cross-cutting behaviour: friendly game errors and a safety net for crashes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from baleropy.dispatcher import BaseMiddleware
from baleropy.exceptions import BaleAPIError, CancelHandler, SkipHandler
from baleropy.types import CallbackQuery, Message

from ..game.services.expedition import ExpeditionService
from ..shared.errors import AwayError, GameError
from ..shared.text import fa
from . import keyboards
from ..shared.text import headline

log = logging.getLogger("eternal_realm.bot")

GENERIC_ERROR = "😵 اوه! طوفانی در قلمرو وزید و کار نیمه‌کاره ماند. نگران نباشید، چند لحظه دیگر دوباره امتحان کنید."


class ErrorMiddleware(BaseMiddleware):
    """Turns :class:`GameError` into a reply and logs everything unexpected."""

    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        try:
            return await handler(event, data)
        except (SkipHandler, CancelHandler):
            raise  # flow control of the framework, not an error
        except AwayError as error:
            await self._tell(event, error.message, self._recall_buttons(event, error))
        except GameError as error:
            await self._tell(event, error.message)
        except BaleAPIError:
            log.exception("Bale API error while handling an update")
        except Exception:
            log.exception("Unhandled error while handling an update")
            await self._tell(event, GENERIC_ERROR)
        return None

    @staticmethod
    def _recall_buttons(event: Any, error: AwayError) -> list | None:
        """The glass button under the «your hero is away» notice: bring the hero back at once for crystals."""
        user = getattr(event, "from_user", None)
        if user is None or error.left <= 0:
            return None
        cost = ExpeditionService.recall_cost(error.left)
        return [[keyboards.panel_button(f"⏪ احضار سریع ({fa(cost)} کریستال)", "awayq", user.id)]]

    @staticmethod
    async def _tell(event: Any, text: str, buttons: list | None = None) -> None:
        try:
            if isinstance(event, CallbackQuery):
                if len(text) <= 190 and not buttons:
                    await event.answer(text, show_alert=True)
                else:
                    await event.answer("⚠️ پیام را در گفتگو بخوانید 👇", show_alert=False)
                    if event.message is not None:
                        if buttons:
                            await event.message.answer(text, buttons=buttons)
                        else:
                            await event.message.answer(text)
            elif isinstance(event, Message):
                if buttons:
                    await event.reply(headline(text), buttons=buttons)
                else:
                    await event.reply(headline(text))
        except BaleAPIError:
            log.warning("could not deliver an error message", exc_info=True)


class UserLockMiddleware(BaseMiddleware):
    """Handles one update at a time per player.

    Two fast taps (or two devices) can no longer interleave halfway through a purchase, a claim or an
    animation; the second tap simply waits for the first to finish and then sees the new state.
    """

    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}
        self._waiting: dict[int, int] = {}

    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        uid = user.id
        lock = self._locks.setdefault(uid, asyncio.Lock())
        self._waiting[uid] = self._waiting.get(uid, 0) + 1
        try:
            async with lock:
                return await handler(event, data)
        finally:
            self._waiting[uid] -= 1
            if not self._waiting[uid]:  # nobody queued: forget the lock so the table never grows
                self._waiting.pop(uid, None)
                self._locks.pop(uid, None)

"""Small illustrations that go with panels: an item you are about to buy, a boss that has been summoned...

The pictures are made by ``tools/gen_art.py`` and live in ``eternal_realm/assets/art/<kind>/<id>.jpg``. A screen asks
for one by name (``"items/wooden_sword"``); when the picture does not exist the screen simply stays text-only.
"""

from __future__ import annotations

import contextlib
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Any

from baleropy.exceptions import BaleAPIError
from baleropy.types import FSInputFile
from baleropy.types.markup import _build_inline_markup

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent / "assets" / "art"
CAPTION_LIMIT = 1024

_file_ids: dict[str, str] = {}  # art name -> Bale file id, so a picture is uploaded once
_shown: OrderedDict[tuple[int, int], str] = OrderedDict()  # (chat, message) -> art name currently on that photo


def path(name: str | None) -> Path | None:
    if not name or ".." in name or name.startswith("/"):
        return None
    file = ROOT / f"{name}.jpg"
    return file if file.is_file() else None


def has(name: str | None) -> bool:
    return path(name) is not None


def _remember(message: Any, name: str) -> None:
    _shown[(message.chat.id, message.message_id)] = name
    while len(_shown) > 4000:
        _shown.popitem(last=False)


def _file_id_of(message: Any) -> str | None:
    photos = getattr(message, "photo", None) or []
    return photos[-1].file_id if photos else None


async def send_chat(bot: Any, chat_id: int, name: str, caption: str, buttons: Any = None, reply_to: int | None = None) -> Any | None:
    """Sends the picture with a caption and buttons to a chat.

    Returns the sent message, or ``None`` when there is no picture for ``name`` or Bale refused it (the caller then
    sends plain text).
    """
    file = path(name)
    if file is None or len(caption) > CAPTION_LIMIT:
        return None
    cached = _file_ids.get(name)
    for source in ([cached] if cached else []) + [FSInputFile(file)]:
        try:
            sent = await bot.send_photo(chat_id, source, caption, reply_to, _markup(buttons) if buttons else None)
        except BaleAPIError:
            _file_ids.pop(name, None)
            continue
        if (fid := _file_id_of(sent)) is not None:
            _file_ids[name] = fid
        _remember(sent, name)
        return sent
    log.warning("could not send picture %s", name)
    return None


async def send(target: Any, name: str, caption: str, buttons: Any = None, reply: bool = False) -> Any | None:
    """Like :func:`send_chat`, in the chat of ``target`` (a Message)."""
    return await send_chat(target.bot, target.chat.id, name, caption, buttons, target.message_id if reply else None)


async def edit_chat(bot: Any, chat_id: int, message_id: int, name: str | None, text: str, buttons: Any = None) -> None:
    """Edits a message that :func:`send_chat` posted (a photo) or, without a picture, a plain text message."""
    if has(name) and len(text) <= CAPTION_LIMIT:
        try:
            await bot.edit_message_caption(chat_id, message_id, text, buttons=buttons or None)
            return
        except BaleAPIError:
            pass  # the picture could not be sent at the time: the message is plain text
    if buttons:
        await bot.edit_message_text(chat_id, message_id, text, buttons=buttons)
    else:
        await bot.edit_message_text(chat_id, message_id, text)


def _markup(rows: Any) -> Any:
    return _build_inline_markup(rows) if isinstance(rows, list) else rows


async def show(message: Any, text: str, rows: Any, name: str | None) -> Any:
    """Puts a panel on screen in place of ``message``, with the picture ``name`` when there is one.

    Telegram-style messages cannot turn from text into a photo or back, so then the old message is replaced.
    """
    is_photo = bool(getattr(message, "photo", None))
    wanted = name if has(name) and len(text) <= CAPTION_LIMIT else None
    key = (message.chat.id, message.message_id)
    if wanted is None and not is_photo:
        return await message.edit_text(text, buttons=rows or None)
    if wanted is not None and is_photo and _shown.get(key) == wanted:
        result = await message.edit_caption(text, buttons=rows or None)
        if hasattr(result, "message_id"):
            _remember(result, wanted)
        return result
    sent = await send(message, wanted, text, rows) if wanted else await message.answer(text, buttons=rows or None)
    if sent is None:  # picture could not be sent: fall back to text
        sent = await message.answer(text, buttons=rows or None)
    with contextlib.suppress(BaleAPIError):
        await message.delete()
    _shown.pop(key, None)
    return sent

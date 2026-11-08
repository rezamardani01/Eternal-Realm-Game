"""Group boss UI: sign-up message, join/start buttons and the loop that plays the fights."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy import Bot, Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery, Message

from ..game.services.bosses import BossUpdate, BossView
from . import keyboards, views
from .callbacks import BossCb
from .services import Services

log = logging.getLogger("eternal_realm.boss")
router = Router(name="boss")


def text_for(services: Services, view: BossView) -> str:
    b = services.ctx.balance
    if view.phase == "recruiting":
        return views.boss_recruiting(view, b.boss_min_players, b.boss_max_players)
    if view.phase == "fighting":
        return views.boss_fight(view)
    return views.boss_final(view)


def buttons_for(view: BossView) -> keyboards.Rows | None:
    return keyboards.boss_buttons(view.id) if view.phase == "recruiting" else None


async def post(message: Message, services: Services, view: BossView) -> Message:
    """Send the boss message and remember it, so the processor can keep editing it."""
    text, buttons = text_for(services, view), buttons_for(view)
    sent = await message.answer(text, buttons=buttons) if buttons else await message.answer(text)
    await services.bosses.attach_message(view.id, sent.message_id)
    return sent


async def _edit(bot: Bot, services: Services, view: BossView) -> None:
    if view.message_id is None:
        return
    text, buttons = text_for(services, view), buttons_for(view)
    with contextlib.suppress(BaleAPIError):  # a missed edit is harmless: the next report fixes it
        if buttons:
            await bot.edit_message_text(view.chat_id, view.message_id, text, buttons=buttons)
        else:
            await bot.edit_message_text(view.chat_id, view.message_id, text)


@router.callback_query(BossCb.filter())
async def on_boss_button(query: CallbackQuery, callback_data: BossCb, services: Services) -> None:
    player = await services.players.require(query.from_user.id)
    if callback_data.action == "join":
        view = await services.bosses.join(callback_data.id, player)
        toast = "⚔️ به نبرد پیوستید!"
    elif callback_data.action == "start":
        view = await services.bosses.start(callback_data.id, player)
        toast = "🚀 نبرد شروع شد!"
    else:
        await query.answer()
        return
    if query.message is not None:
        text, buttons = text_for(services, view), buttons_for(view)
        with contextlib.suppress(BaleAPIError):
            if buttons:
                await query.message.edit_text(text, buttons=buttons)
            else:
                await query.message.edit_text(text)
    await query.answer(toast)


async def apply_updates(bot: Bot, services: Services, updates: list[BossUpdate]) -> None:
    for update in updates:
        await _edit(bot, services, update.view)


async def processor(bot: Bot, services: Services, interval: float = 3.0) -> None:
    """The single central loop: every few seconds advance whichever fights are due."""
    while True:
        try:
            await apply_updates(bot, services, await services.bosses.process_due())
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("boss processor failed")
        await asyncio.sleep(interval)

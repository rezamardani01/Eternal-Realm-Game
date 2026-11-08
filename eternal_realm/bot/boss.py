"""Group boss UI: sign-up message, join/start buttons and the loop that plays the fights."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy import Bot, Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery, Message

from ..game.services.bosses import BossUpdate, BossView
from ..shared.text import bold, fa
from . import art, keyboards, views
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


def portrait_caption(view: BossView) -> str:
    t = view.type
    return f"{t.emoji} {bold(t.name)}\nسطح {fa(view.level)} · {t.element.emoji} {t.element.noun}"


def buttons_for(view: BossView) -> keyboards.Rows | None:
    if view.phase == "recruiting":
        return keyboards.boss_buttons(view.id)
    if view.phase == "ended" and view.outcome != "cancelled":
        return keyboards.boss_result(view)
    return None


async def _replace(bot: Bot, services: Services, view: BossView, text: str, old_message_id: int | None) -> None:
    """Remove the old boss message and send a fresh one at the bottom of the chat."""
    if old_message_id is not None:
        with contextlib.suppress(BaleAPIError):
            await bot.delete_message(view.chat_id, old_message_id)
    buttons = buttons_for(view)
    try:
        if buttons:
            sent = await bot.send_message(view.chat_id, text, buttons=buttons)
        else:
            sent = await bot.send_message(view.chat_id, text)
    except BaleAPIError:
        log.warning("could not post boss message in chat %s", view.chat_id)
        return
    await services.bosses.attach_message(view.id, sent.message_id)


async def post(message: Message, services: Services, view: BossView) -> Message:
    """Send the boss message and remember it, so the processor can keep editing it."""
    t = view.type
    await art.send(message, f"bosses/{t.id}", portrait_caption(view))
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
async def on_boss_button(query: CallbackQuery, callback_data: BossCb, services: Services, bot: Bot) -> None:
    if callback_data.action == "info":
        await query.answer()
        return
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
    if callback_data.action == "start" and query.message is not None:
        await _replace(bot, services, view, views.boss_started(view), query.message.message_id)
    elif query.message is not None:
        text, buttons = text_for(services, view), buttons_for(view)
        with contextlib.suppress(BaleAPIError):
            if buttons:
                await query.message.edit_text(text, buttons=buttons)
            else:
                await query.message.edit_text(text)
    await query.answer(toast)


async def apply_updates(bot: Bot, services: Services, updates: list[BossUpdate]) -> None:
    for update in updates:
        if update.kind == "started":
            await _replace(bot, services, update.view, views.boss_started(update.view), update.view.message_id)
        elif update.kind == "final" and update.view.outcome != "cancelled":
            await _replace(bot, services, update.view, text_for(services, update.view), update.view.message_id)
        else:
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

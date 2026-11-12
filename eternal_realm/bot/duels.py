"""Inline-button handling for duels, plus the janitor that closes stale ones."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from baleropy import Bot, Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery

from ..game.engine.combat import Action
from ..game.services.duels import Duel, DuelUpdate
from ..shared.errors import GameError
from . import keyboards, views
from .callbacks import DuelCb
from .services import Services

log = logging.getLogger("eternal_realm.duels")
router = Router(name="duels")

ACTIONS = {
    "attack": Action.ATTACK,
    "skill1": Action.SKILL1,
    "skill2": Action.SKILL2,
    "skill3": Action.SKILL3,
    "defend": Action.DEFEND,
    "surrender": Action.SURRENDER,
}


def render(update: DuelUpdate, turn_seconds: int) -> tuple[str, keyboards.Rows | None]:
    if update.finished:
        return views.duel_result(update), keyboards.duel_result(update)
    text = views.duel_status(update.battle, update.lines, turn_seconds)
    return text, keyboards.duel_actions(update.duel.id, update.battle.current)


@router.callback_query(DuelCb.filter())
async def on_duel_button(query: CallbackQuery, callback_data: DuelCb, services: Services) -> None:
    message = query.message
    if message is None:
        await query.answer()
        return
    player = await services.players.require(query.from_user.id)
    turn_seconds = services.ctx.balance.duel_turn_seconds
    duel_id, action = callback_data.id, callback_data.action

    if action == "accept":
        update = await services.duels.accept(duel_id, player)
        text, buttons = render(update, turn_seconds)
        await message.edit_text(text, buttons=buttons)
    elif action == "decline":
        duel = await services.duels.decline(duel_id, player)
        who = "را نپذیرفت" if player.id == duel.target_id else "را پس گرفت"
        await message.edit_text(f"🏳️ فراخوان دوئل بی‌نتیجه ماند؛ فرمانده‌ی مقابل آن {who}. شاید در فرصتی دیگر!")
    elif action == "info":
        pass
    elif action == "rematch":
        duel = await services.duels.get(duel_id)
        if duel is None or player.id not in (duel.challenger_id, duel.target_id):
            raise GameError("فقط دو جنگجوی همین نبرد می‌توانند دوباره مبارزه را بخواهند.")
        other = await services.players.get(duel.target_id if player.id == duel.challenger_id else duel.challenger_id)
        if other is None:
            raise GameError("حریف شما دیگر در قلمرو نیست.")
        fresh = await services.duels.challenge(message.chat.id, player, other)
        seconds = services.ctx.balance.duel_invite_seconds
        sent = await message.answer(views.duel_invite(player, other, seconds), buttons=keyboards.duel_invite(fresh.id))
        await services.duels.attach_message(fresh.id, sent.message_id)
        await query.answer("⚔️ فراخوان تازه فرستاده شد!")
        return
    elif action in ACTIONS:
        update = await services.duels.act(duel_id, player, ACTIONS[action])
        text, buttons = render(update, turn_seconds)
        if update.finished:  # the fight message goes away and the result arrives as a fresh one
            with contextlib.suppress(BaleAPIError):
                await message.delete()
            sent = await message.answer(text, buttons=buttons) if buttons else await message.answer(text)
            await services.duels.attach_message(duel_id, sent.message_id)
        else:
            await message.edit_text(text, buttons=buttons)
    else:
        raise GameError("این دکمه از کار افتاده است؛ فرمان تازه‌ای بدهید.")
    await query.answer()


async def _announce(bot: Bot, services: Services, item: DuelUpdate | Duel) -> None:
    duel = item.duel if isinstance(item, DuelUpdate) else item
    if duel.message_id is None:
        return
    if isinstance(item, DuelUpdate):
        text = views.duel_result(item)
    else:
        text = "⌛ فراخوان دوئل بی‌پاسخ ماند و در باد گم شد. هر وقت خواستید دوباره دعوت کنید!"
    buttons = keyboards.duel_result(item) if isinstance(item, DuelUpdate) else None
    with contextlib.suppress(BaleAPIError):
        if isinstance(item, DuelUpdate) and item.finished:
            await bot.delete_message(duel.chat_id, duel.message_id)
            await bot.send_message(duel.chat_id, text, buttons=buttons) if buttons else await bot.send_message(duel.chat_id, text)
        elif buttons:
            await bot.edit_message_text(duel.chat_id, duel.message_id, text, buttons=buttons)
        else:
            await bot.edit_message_text(duel.chat_id, duel.message_id, text)


async def janitor(bot: Bot, services: Services, interval: float = 20.0) -> None:
    """Every few seconds close unanswered invitations and duels whose turn timer ran out."""
    while True:
        try:
            for item in await services.duels.expire_stale():
                await _announce(bot, services, item)
            from .bet_panel import announce_expired

            await announce_expired(bot, services)
            from .team_battle import announce as announce_teams

            await announce_teams(bot, services)
            await services.payments.expire_stale()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("duel janitor failed")
        await asyncio.sleep(interval)

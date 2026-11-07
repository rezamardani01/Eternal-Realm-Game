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
    "skill": Action.SKILL,
    "defend": Action.DEFEND,
    "surrender": Action.SURRENDER,
}


def render(update: DuelUpdate, turn_seconds: int) -> tuple[str, keyboards.Rows | None]:
    if update.finished:
        return views.duel_result(update), None
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
        who = "رد شد" if player.id == duel.target_id else "لغو شد"
        await message.edit_text(f"❌ درخواست مبارزه {who}.")
    elif action in ACTIONS:
        update = await services.duels.act(duel_id, player, ACTIONS[action])
        text, buttons = render(update, turn_seconds)
        await message.edit_text(text, buttons=buttons)
    else:
        raise GameError("دکمه نامعتبر است.")
    await query.answer()


async def _announce(bot: Bot, services: Services, item: DuelUpdate | Duel) -> None:
    duel = item.duel if isinstance(item, DuelUpdate) else item
    if duel.message_id is None:
        return
    if isinstance(item, DuelUpdate):
        text = views.duel_result(item)
    else:
        text = "⌛ درخواست مبارزه بی‌پاسخ ماند و بسته شد."
    with contextlib.suppress(BaleAPIError):
        await bot.edit_message_text(duel.chat_id, duel.message_id, text)


async def janitor(bot: Bot, services: Services, interval: float = 20.0) -> None:
    """Every few seconds close unanswered invitations and duels whose turn timer ran out."""
    while True:
        try:
            for item in await services.duels.expire_stale():
                await _announce(bot, services, item)
            await services.payments.expire_stale()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("duel janitor failed")
        await asyncio.sleep(interval)

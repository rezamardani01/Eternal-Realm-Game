"""Group boss UI: posting the boss message, the hit buttons and the end-of-fight announcement."""

from __future__ import annotations

import contextlib
import logging

from baleropy import Bot, Router
from baleropy.exceptions import BaleAPIError
from baleropy.types import CallbackQuery, Message

from ..game.services.bosses import BossView
from ..shared.text import fa
from . import keyboards, views
from .callbacks import BossCb
from .services import Services

log = logging.getLogger("eternal_realm.boss")
router = Router(name="boss")


def buttons_for(services: Services, view: BossView) -> keyboards.Rows:
    b = services.ctx.balance
    return keyboards.boss_buttons(view.id, b.boss_hit_energy, b.boss_heavy_energy)


async def post(message: Message, services: Services, view: BossView, text: str | None = None) -> Message:
    """Send the boss message to the chat and remember it, so it can be edited as the fight goes on."""
    sent = await message.answer(text or views.boss_status(view), buttons=buttons_for(services, view))
    await services.bosses.attach_message(view.id, sent.message_id)
    return sent


@router.callback_query(BossCb.filter())
async def on_boss_button(query: CallbackQuery, callback_data: BossCb, services: Services) -> None:
    player = await services.players.require(query.from_user.id)
    result = await services.bosses.hit(callback_data.id, player, heavy=callback_data.action == "heavy")
    view = result.view
    last = (
        f"{'💥' if result.heavy else '⚔️'} {player.name}: {fa(result.damage)} آسیب"
        + (" (ضربه‌ی کاری!)" if result.crit else "")
    )
    if query.message is not None:
        with contextlib.suppress(BaleAPIError):  # many players tap at once; a missed edit is harmless
            if result.finished:
                await query.message.edit_text(views.boss_final(view))
            else:
                await query.message.edit_text(views.boss_status(view, last), buttons=buttons_for(services, view))
    toast = f"{'💥' if result.heavy else '⚔️'} {fa(result.damage)} آسیب زدید" + (" — ضربه‌ی کاری!" if result.crit else "")
    await query.answer(toast)


async def announce_expired(bot: Bot, services: Services) -> None:
    """Called by the janitor: bosses that ran out of time flee and their message says so."""
    for view in await services.bosses.expire_stale():
        if view.message_id is not None:
            with contextlib.suppress(BaleAPIError):
                await bot.edit_message_text(view.chat_id, view.message_id, views.boss_final(view))

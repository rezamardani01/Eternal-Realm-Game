"""Inline-button handling for the shop (gear upgrades)."""

from __future__ import annotations

from baleropy import Router
from baleropy.types import CallbackQuery

from . import views
from .callbacks import UpgradeCb
from .services import Services

router = Router(name="shop")


@router.callback_query(UpgradeCb.filter())
async def on_upgrade(query: CallbackQuery, callback_data: UpgradeCb, services: Services) -> None:
    player = await services.players.require(query.from_user.id)
    result = await services.shop.upgrade(player, callback_data.id, callback_data.level)
    if query.message is not None:
        await query.message.edit_text(views.upgrade_result(result))
    await query.answer("✅ ارتقا موفق!" if result.success else "💥 ارتقا شکست خورد", show_alert=False)
